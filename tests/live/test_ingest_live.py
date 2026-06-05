import numpy as np
import pandas as pd

from wcmodel.data.sources.results import normalize_results
from wcmodel.data.store import BitemporalStore, Policy
from wcmodel.data.tournament import WC2026_SOURCE
from wcmodel.live.ingest_live import ingest_live_result


def _store(tmp_path):
    return BitemporalStore(tmp_path / "store")


def test_ingest_live_result_writes_actual_score_point_in_time(tmp_path):
    store = _store(tmp_path)
    # A finished group fixture: Brazil 2-0 Croatia, observed AT the final whistle.
    n = ingest_live_result(
        store, home_team="Brazil", away_team="Croatia",
        date="2026-06-11", home_score=2, away_score=0,
        tournament="FIFA World Cup", neutral=True, city="Inglewood",
        country="United States", observed_at="2026-06-11T21:00:00Z",
    )
    assert n == 1
    # POINT_IN_TIME: visible AT/after the final whistle, invisible BEFORE it.
    after = store.read("results", cutoff="2026-06-12")
    row = after[(after["home_team"] == "Brazil") & (after["away_team"] == "Croatia")]
    assert len(row) == 1
    assert int(row["home_score"].iloc[0]) == 2 and int(row["away_score"].iloc[0]) == 0
    # Leakage-safe: a read BEFORE the observed final whistle does NOT see the result.
    before = store.read("results", cutoff="2026-06-11T20:00:00Z")
    assert before[(before["home_team"] == "Brazil")
                  & (before["away_team"] == "Croatia")].empty


def test_ingest_live_knockout_carries_shootout_winner(tmp_path):
    store = _store(tmp_path)
    # A level-after-ET knockout decided on penalties: the ACTUAL winner is recorded
    # in winner_override (post-L3, consumed by the sim's D3 fix in Task 7).
    n = ingest_live_result(
        store, home_team="Brazil", away_team="Argentina",
        date="2026-06-28", home_score=1, away_score=1,
        tournament="FIFA World Cup", neutral=True, city="East Rutherford",
        country="United States", observed_at="2026-06-28T23:00:00Z",
        winner_override="Brazil",
    )
    assert n == 1
    res = store.read("results", cutoff="2026-06-29")
    row = res[(res["home_team"] == "Brazil") & (res["away_team"] == "Argentina")]
    assert row["winner_override"].iloc[0] == "Brazil"


def test_ingest_live_result_updates_schedule_row_same_match_id(tmp_path):
    store = _store(tmp_path)
    # The pre-existing UNPLAYED schedule row, written exactly as
    # ingest_wc_group_fixtures writes it (NaN score, normalize_results keying,
    # WC2026_SOURCE). The live result must update THIS row's key, not duplicate it.
    sched_raw = pd.DataFrame(
        [{"date": "2026-06-11", "home_team": "Brazil", "away_team": "Croatia",
          "home_score": np.nan, "away_score": np.nan, "tournament": "FIFA World Cup",
          "neutral": True, "city": "Inglewood", "country": "United States"}],
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "neutral", "city", "country"],
    )
    sched = normalize_results(sched_raw)
    sched_match_id = sched["match_id"].iloc[0]
    store.write("results", sched, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source=WC2026_SOURCE, source_version=WC2026_SOURCE)

    # Live-ingest the SAME finished fixture's actual result.
    ingest_live_result(
        store, home_team="Brazil", away_team="Croatia",
        date="2026-06-11", home_score=2, away_score=0,
        tournament="FIFA World Cup", neutral=True, city="Inglewood",
        country="United States", observed_at="2026-06-11T21:00:00Z",
    )

    # Same-key, idempotent: append-only store has both rows but ONE logical key.
    raw = pd.read_parquet(store._path("results"))
    live_match_id = raw[raw["source"] == "wc2026_live"]["match_id"].iloc[0]
    assert live_match_id == sched_match_id          # identical keying to the schedule row
    assert raw["match_id"].nunique() == 1           # not a duplicate fixture

    # <cutoff discipline unchanged: BEFORE the whistle the read still returns the
    # UNPLAYED schedule row (NaN score); AFTER, the actual result supersedes it.
    before = store.read("results", cutoff="2026-06-11T20:00:00Z")
    brow = before[before["match_id"] == sched_match_id]
    assert len(brow) == 1 and pd.isna(brow["home_score"].iloc[0])
    after = store.read("results", cutoff="2026-06-12")
    arow = after[after["match_id"] == sched_match_id]
    assert len(arow) == 1
    assert int(arow["home_score"].iloc[0]) == 2 and int(arow["away_score"].iloc[0]) == 0


def test_ingest_refuses_unplayed_result(tmp_path):
    store = _store(tmp_path)
    # An unplayed (NaN-score) "result" is a schedule row, NOT a live result — refuse it
    # so the writer can only ever record an ACTUAL played result.
    import pytest
    with pytest.raises(ValueError, match="(?i)unplayed|nan|score"):
        ingest_live_result(
            store, home_team="X", away_team="Y", date="2026-06-20",
            home_score=np.nan, away_score=np.nan, tournament="FIFA World Cup",
            neutral=True, city="Foxborough", country="United States",
            observed_at="2026-06-20T21:00:00Z",
        )


def test_ingest_refuses_future_observed_at(tmp_path):
    store = _store(tmp_path)
    # observed_at must be >= kickoff date: a result cannot be "known" before it is played.
    import pytest
    with pytest.raises(ValueError, match="(?i)observed_at|before|kickoff|played"):
        ingest_live_result(
            store, home_team="X", away_team="Y", date="2026-06-20",
            home_score=1, away_score=0, tournament="FIFA World Cup",
            neutral=True, city="Foxborough", country="United States",
            observed_at="2026-06-19T12:00:00Z",   # BEFORE the match date => refused
        )


# ---------------------------------------------------------------------------
# FIX 1 (store-level tz leak) — read() must normalize a tz-aware NON-UTC cutoff
# to naive-UTC so it can never parse as next-day naive time and leak a future
# observed_at result. The whistle is 2026-06-11T21:00Z; a +08:00 cutoff of
# 2026-06-12T01:00+08:00 is 2026-06-11T17:00Z — BEFORE the whistle — so it must
# see 0 played rows. Without the fix the aware string drops its offset in the
# DuckDB `TIMESTAMP '...'` literal and reads as 2026-06-12 01:00 naive => LEAK.
# ---------------------------------------------------------------------------
def test_read_aware_non_utc_cutoff_does_not_leak_future_result(tmp_path):
    store = _store(tmp_path)
    # The actual result, observed AT the 21:00Z final whistle (T2 ingest path).
    ingest_live_result(
        store, home_team="Brazil", away_team="Croatia",
        date="2026-06-11", home_score=2, away_score=0,
        tournament="FIFA World Cup", neutral=True, city="Inglewood",
        country="United States", observed_at="2026-06-11T21:00:00Z",
    )
    # A +08:00 cutoff that is 2026-06-11T17:00Z — strictly BEFORE the whistle.
    aware_non_utc = pd.Timestamp("2026-06-12T01:00:00+08:00")  # == 2026-06-11T17:00Z
    out = store.read("results", cutoff=aware_non_utc)
    leaked = out[(out["home_team"] == "Brazil") & (out["away_team"] == "Croatia")]
    assert leaked.empty, "non-UTC aware cutoff before the whistle leaked the future result"

    # No regression: a naive cutoff and an aware-UTC `Z` cutoff naming the SAME
    # instant (2026-06-11T17:00Z) behave identically — both BEFORE the whistle.
    naive = store.read("results", cutoff="2026-06-11T17:00:00")
    aware_z = store.read("results", cutoff=pd.Timestamp("2026-06-11T17:00:00Z"))
    for r in (naive, aware_z):
        assert r[(r["home_team"] == "Brazil") & (r["away_team"] == "Croatia")].empty


# ---------------------------------------------------------------------------
# FIX 2 (idempotency for timestamp dates) — a live result whose `date` is a
# FULL TIMESTAMP must hash to the SAME match_id as the date-only schedule row
# (an UPDATE, not a duplicate). Without canonicalizing the date to its calendar
# day, sha1("2026-06-11T21:00:00Z|...") != sha1("2026-06-11|...") => 2 keys.
# ---------------------------------------------------------------------------
def test_ingest_timestamp_date_keys_same_match_id_as_schedule(tmp_path):
    store = _store(tmp_path)
    # Pre-existing UNPLAYED schedule row keyed off the date-only "2026-06-11".
    sched_raw = pd.DataFrame(
        [{"date": "2026-06-11", "home_team": "Brazil", "away_team": "Croatia",
          "home_score": np.nan, "away_score": np.nan, "tournament": "FIFA World Cup",
          "neutral": True, "city": "Inglewood", "country": "United States"}],
        columns=["date", "home_team", "away_team", "home_score", "away_score",
                 "tournament", "neutral", "city", "country"],
    )
    sched = normalize_results(sched_raw)
    sched_match_id = sched["match_id"].iloc[0]
    store.write("results", sched, policy=Policy.POINT_IN_TIME, keys=["match_id"],
                source=WC2026_SOURCE, source_version=WC2026_SOURCE)

    # Live-ingest the SAME fixture but pass a FULL-TIMESTAMP date (with the whistle
    # time-of-day) — the canonical calendar day must still match the schedule key.
    ingest_live_result(
        store, home_team="Brazil", away_team="Croatia",
        date="2026-06-11T21:00:00Z", home_score=2, away_score=0,
        tournament="FIFA World Cup", neutral=True, city="Inglewood",
        country="United States", observed_at="2026-06-11T21:00:00Z",
    )

    raw = pd.read_parquet(store._path("results"))
    live_match_id = raw[raw["source"] == "wc2026_live"]["match_id"].iloc[0]
    assert live_match_id == sched_match_id      # full-timestamp date -> same key
    assert raw["match_id"].nunique() == 1       # an UPDATE, not a duplicate fixture


# ---------------------------------------------------------------------------
# FIX 3 (finite/non-negative/integral scores) — `int()` truncation/negatives
# are refused via the shared valid_played_results rule.
# ---------------------------------------------------------------------------
def test_ingest_refuses_fractional_score(tmp_path):
    store = _store(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="(?i)score|integ|finite|non-negative|valid"):
        ingest_live_result(
            store, home_team="X", away_team="Y", date="2026-06-20",
            home_score=2.5, away_score=0, tournament="FIFA World Cup",
            neutral=True, city="Foxborough", country="United States",
            observed_at="2026-06-20T21:00:00Z",
        )


def test_ingest_refuses_negative_score(tmp_path):
    store = _store(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="(?i)score|integ|finite|non-negative|valid"):
        ingest_live_result(
            store, home_team="X", away_team="Y", date="2026-06-20",
            home_score=-1, away_score=0, tournament="FIFA World Cup",
            neutral=True, city="Foxborough", country="United States",
            observed_at="2026-06-20T21:00:00Z",
        )


# ---------------------------------------------------------------------------
# FIX 4 (inclusive as-of-now boundary) — read AS-OF exactly the whistle SEES
# the result (observed_at <= cutoff); one microsecond before does NOT.
# ---------------------------------------------------------------------------
def test_read_at_whistle_is_inclusive_one_microsecond_before_is_not(tmp_path):
    store = _store(tmp_path)
    ingest_live_result(
        store, home_team="Brazil", away_team="Croatia",
        date="2026-06-11", home_score=2, away_score=0,
        tournament="FIFA World Cup", neutral=True, city="Inglewood",
        country="United States", observed_at="2026-06-11T21:00:00Z",
    )
    whistle = pd.Timestamp("2026-06-11T21:00:00")        # naive UTC == observed_at
    at = store.read("results", cutoff=whistle)
    arow = at[(at["home_team"] == "Brazil") & (at["away_team"] == "Croatia")]
    assert len(arow) == 1                                # inclusive as-of-now: SEES it
    assert int(arow["home_score"].iloc[0]) == 2 and int(arow["away_score"].iloc[0]) == 0

    just_before = whistle - pd.Timedelta(microseconds=1)
    bf = store.read("results", cutoff=just_before)
    assert bf[(bf["home_team"] == "Brazil") & (bf["away_team"] == "Croatia")].empty
