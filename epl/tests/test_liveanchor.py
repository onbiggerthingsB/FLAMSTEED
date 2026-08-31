"""The explicit season transition and the live Elo walk (plan v2 D5 / T2, P0-1).

WHAT THIS FILE IS DEFENDING. `epl.anchor.Anchor` is built from an archive of
COMPLETED seasons and its season-boundary rule fires on a change of the season
label while walking the rows it was given. Two things follow, and both are
wrong for a season that is being played right now:

1. Asked for a cutoff past the last archived match, `Anchor.state` returns
   `_final_ratings()` — the post-2025/26 table with NO re-seeding. Coventry
   raises `KeyError` (never in the archive), Hull carries its 2016/17 rating and
   Ipswich its relegated-season rating, whereas the frozen protocol seeds a
   promoted club at `division_mean + promoted_offset`.
2. `epl.elo._open_season` derives the season's club set from the ROWS PRESENT.
   Feed it a partial live season and it re-seeds only the clubs that have
   already kicked off; the other seventeen never get their summer boundary.

So the tests below are not "does the module import". They are: does the
transition put every one of the twenty manifest clubs on the protocol's own
scale before a single ball is kicked, does the live walk keep them all there
when only one fixture has been played, and — the one that licenses duplicating
`compute_elo_history`'s update loop — does an EXPLICIT replay of 2025/26
reproduce the archived `Anchor` snapshots bitwise.

EVERY GUARD CARRIES ITS POSITIVE CONTROL. The transition tests assert the BUG
as well as the fix (plain `Anchor` really does hand out Hull's 2016/17 rating);
the bitwise parity test asserts that a one-point change in K makes the same
comparison FAIL. A canary that cannot fail is a bug.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_liveanchor.py -q
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from epl import anchor as anchor_mod, baseline, elo as epl_elo, freeze
from epl import liveanchor as la
from epl import paths, score as score_mod, season as season_mod
from epl.schema import sort_for_walk_forward

SEASON = "2026/27"
SEASON_CODE = "2627"
OPENER = "2026-08-21"
PREV_SEASON = "2025/26"

#: Measured on the real archive (4,560 rows through 2026-05-24) under the frozen
#: Elo configuration — the numbers the adjudication quotes for Codex P0-1.
HULL_STALE = 1398.93
IPSWICH_STALE = 1411.08
DIVISION_MEAN_2627 = 1594.61
PROMOTED_SEED_2627 = 1519.61

needs_archive = pytest.mark.skipif(
    not paths.MATCHES_PARQUET.exists(),
    reason="archive parquet absent (data/epl is gitignored)")


# ==========================================================================
# fixtures / helpers
# ==========================================================================
@pytest.fixture(scope="module")
def cfg() -> epl_elo.EloConfig:
    return freeze.frozen_elo_config()


@pytest.fixture(scope="module")
def played() -> pd.DataFrame:
    matches = baseline.load_matches()
    return sort_for_walk_forward(matches.loc[matches["played"]])


@pytest.fixture(scope="module")
def manifest() -> season_mod.Manifest:
    return season_mod.load_manifest(SEASON)


def _clubs(frame: pd.DataFrame, season: str) -> set[str]:
    rows = frame.loc[frame["season"] == season]
    return set(rows["home_key"]) | set(rows["away_key"])


def _synthetic_manifest(frame: pd.DataFrame, season: str,
                        prev: str) -> season_mod.Manifest:
    """A `Manifest` for an ARCHIVED season, so the production transition path
    can be pointed at a season whose answer is already known."""
    clubs = _clubs(frame, season)
    prev_clubs = _clubs(frame, prev)
    return season_mod.Manifest(
        season=season, season_code=season_mod.season_code(season),
        clubs=tuple(sorted(clubs)),
        promoted=tuple(sorted(clubs - prev_clubs)),
        relegated=tuple(sorted(prev_clubs - clubs)),
        prev_season=prev, prev_season_clubs=tuple(sorted(prev_clubs)),
        fixtures_filename="", fixtures_sha256="", tiebreak_rule_id="",
        material_boundaries=(), orientation_spotcheck={}, raw={})


def _live_rows_from_frame(frame: pd.DataFrame, code: str) -> list[dict]:
    """Archive rows re-expressed as results-ledger rows (D4 shape)."""
    out = []
    for r in frame.itertuples():
        out.append({
            "fixture_id": season_mod.fixture_id(code, r.home_key, r.away_key),
            "date_played": pd.Timestamp(r.date).normalize(),
            "hg": int(r.fthg), "ag": int(r.ftag),
            "source": "test", "observed_at": pd.Timestamp(r.date).normalize(),
            "note": "",
        })
    return out


# --- a small, fully synthetic archive so the core is testable with no data --
SYNTH_CLUBS = {
    "a1": ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"],
    "a2": ["alpha", "bravo", "charlie", "delta", "echo", "golf"],
    "a3": ["alpha", "bravo", "charlie", "delta", "hotel", "golf"],
}


def _round_robin(clubs: list[str]) -> list[list[tuple[str, str]]]:
    """Circle-method schedule: n-1 matchdays of n/2 matches, then the reverse.

    A real schedule rather than a shuffle, because the block rule under test is
    "several matches are simultaneous and must not inform one another": every
    matchday here holds three matches and no club appears in two of them.
    """
    n = len(clubs)
    assert n % 2 == 0
    arr = list(clubs)
    first: list[list[tuple[str, str]]] = []
    for r in range(n - 1):
        day = []
        for i in range(n // 2):
            h, a = arr[i], arr[n - 1 - i]
            if (r + i) % 2:
                h, a = a, h
            day.append((h, a))
        first.append(day)
        arr = [arr[0], arr[-1], *arr[1:-1]]
    return first + [[(a, h) for h, a in day] for day in first]


def _synthetic_archive() -> pd.DataFrame:
    """Three 6-club seasons, double round-robin, three matches per matchday.

    One club is swapped out each summer so the promoted-seed branch fires.
    """
    rng = np.random.default_rng(20260818)
    rows = []
    day = pd.Timestamp("2023-08-05")
    for si, (season, clubs) in enumerate(
            zip(("2023/24", "2024/25", "2025/26"),
                (SYNTH_CLUBS["a1"], SYNTH_CLUBS["a2"], SYNTH_CLUBS["a3"]))):
        for matchday in _round_robin(clubs):
            for h, a in matchday:
                hg, ag = int(rng.integers(0, 4)), int(rng.integers(0, 4))
                rows.append({
                    "match_id": f"{season}:{h}:{a}", "season": season,
                    "season_code": f"s{si}", "date": day, "time": None,
                    "kickoff": pd.NaT, "home_key": h, "away_key": a,
                    "fthg": hg, "ftag": ag,
                    "ftr": "H" if hg > ag else "A" if ag > hg else "D",
                    "played": True,
                })
            day += pd.Timedelta(days=3)
        day += pd.Timedelta(days=60)            # summer break
    frame = sort_for_walk_forward(pd.DataFrame(rows))
    assert len(frame) == 3 * 30
    return frame


# ==========================================================================
# 1. the replay loop is `compute_elo_history`'s loop — bitwise
# ==========================================================================
def test_replay_reproduces_compute_elo_history_bitwise_on_a_synthetic_archive(cfg):
    frame = _synthetic_archive()
    full = anchor_mod.Anchor(frame, cfg)

    prior = sort_for_walk_forward(frame.loc[frame["season"] != "2025/26"])
    part = anchor_mod.Anchor(prior, cfg)
    mf = _synthetic_manifest(frame, "2025/26", "2024/25")
    ratings = la.open_target_season(part, mf, cfg)

    target = sort_for_walk_forward(frame.loc[frame["season"] == "2025/26"])
    res = la.replay(ratings, target, cfg, promoted=mf.promoted)

    want = [s for s in full._snapshots if s["season"] == "2025/26"]
    assert len(res.snapshots) == len(want) > 1
    for got, exp in zip(res.snapshots, want):
        assert pd.Timestamp(got["key"]) == pd.Timestamp(exp["key"])
        assert set(got["ratings"]) == set(exp["ratings"])
        for club, value in exp["ratings"].items():
            assert float(got["ratings"][club]) == float(value)

    # POSITIVE CONTROL: the comparison above must be able to fail. Replaying
    # with K one point different has to disagree with the archived snapshots.
    off = la.replay(la.open_target_season(part, mf, cfg.replace(k=cfg.k + 1.0)),
                    target, cfg.replace(k=cfg.k + 1.0), promoted=mf.promoted)
    diffs = [club for club, value in want[-1]["ratings"].items()
             if float(off.snapshots[-1]["ratings"][club]) != float(value)]
    assert diffs, "a perturbed K produced identical ratings — the test is inert"


def test_transition_guards_fail_closed_on_a_mismatched_manifest(cfg):
    """Three ways the transition could quietly use the wrong division mean."""
    frame = _synthetic_archive()
    prior = sort_for_walk_forward(frame.loc[frame["season"] != "2025/26"])
    part = anchor_mod.Anchor(prior, cfg)
    good = _synthetic_manifest(frame, "2025/26", "2024/25")
    assert la.open_target_season(part, good, cfg)          # control: valid

    with pytest.raises(la.TransitionError, match="transitions from"):
        la.open_target_season(part, dataclasses.replace(
            good, prev_season="2023/24"), cfg)
    with pytest.raises(la.TransitionError, match="wrong twenty"):
        la.open_target_season(part, dataclasses.replace(
            good, prev_season_clubs=tuple(sorted(SYNTH_CLUBS["a1"]))), cfg)

    short = sort_for_walk_forward(prior.iloc[:-1])         # one match missing
    with pytest.raises(la.TransitionError, match="incomplete"):
        la.open_target_season(anchor_mod.Anchor(short, cfg), good, cfg)


def test_liveanchor_refuses_target_season_rows_in_the_archive(cfg):
    """The target season must arrive through the ledger, never the archive."""
    frame = _synthetic_archive()
    prior = sort_for_walk_forward(frame.loc[frame["season"] != "2025/26"])
    mf = _synthetic_manifest(frame, "2025/26", "2024/25")
    assert la.LiveAnchor(prior, [], mf, cfg).opening_table()   # control: valid
    with pytest.raises(la.TransitionError, match="results ledger"):
        la.LiveAnchor(frame, [], mf, cfg)


def test_replay_refuses_a_club_it_has_no_rating_for(cfg):
    frame = _synthetic_archive()
    target = sort_for_walk_forward(frame.loc[frame["season"] == "2025/26"])
    with pytest.raises(la.TransitionError, match="hotel"):
        la.replay({c: 1500.0 for c in SYNTH_CLUBS["a3"] if c != "hotel"},
                  target, cfg)


# ==========================================================================
# 2. row hygiene and the known-at rule
# ==========================================================================
def test_normalise_rows_rejects_unknown_club_and_bad_score(manifest):
    good = {"fixture_id": f"{SEASON_CODE}:arsenal:coventry",
            "date_played": "2026-08-21", "hg": 2, "ag": 0,
            "observed_at": "2026-08-22"}
    assert len(la.normalise_rows([good], manifest)) == 1      # control: valid

    with pytest.raises(season_mod.SeasonError):
        la.normalise_rows([dict(good, fixture_id=f"{SEASON_CODE}:arsenal:luton")],
                          manifest)
    with pytest.raises(season_mod.SeasonError):
        la.normalise_rows([dict(good, hg=-1)], manifest)
    with pytest.raises(season_mod.SeasonError):
        la.normalise_rows([dict(good, hg=1.5)], manifest)
    with pytest.raises(season_mod.SeasonError):
        la.normalise_rows([{k: v for k, v in good.items()
                            if k != "observed_at"}], manifest)


def test_visible_rows_respect_date_and_observed_at(manifest):
    rows = la.normalise_rows([{
        "fixture_id": f"{SEASON_CODE}:arsenal:coventry",
        "date_played": "2026-08-21", "hg": 2, "ag": 0,
        "observed_at": "2026-08-23"}], manifest)

    # invisible before it was played...
    assert la.visible_rows(rows, "2026-08-21", "2026-08-30") == ()
    # ...invisible before it was OBSERVED, even though it had been played...
    assert la.visible_rows(rows, "2026-08-25", "2026-08-22") == ()
    # ...and visible once both clocks have passed. (Positive control: the two
    # assertions above are not vacuous, this one uses the same row.)
    assert len(la.visible_rows(rows, "2026-08-25", "2026-08-30")) == 1


def test_rows_to_frame_carries_distinct_valid_and_observation_clocks(manifest):
    rows = la.normalise_rows([{
        "fixture_id": f"{SEASON_CODE}:arsenal:coventry",
        "date_played": "2026-08-21", "hg": 2, "ag": 0,
        "observed_at": "2026-08-25T20:55:44+08:00",
    }], manifest)

    frame = la.rows_to_frame(rows, SEASON)

    assert frame.loc[0, "valid_as_of"] == pd.Timestamp("2026-08-21")
    assert frame.loc[0, "observed_at"] == pd.Timestamp("2026-08-25 12:55:44")
    assert frame.loc[0, "observed_at"] != frame.loc[0, "date"]


def test_normalise_rows_refuses_an_observed_at_that_is_not_a_timestamp(manifest):
    """A stamp that will not parse must STOP the load, not become `NaT`.

    `NaT` compares False against every bound, so `observed_at > observed_by` is
    False for it and a row carrying one is visible at every cutoff — the exact
    leak the known-at stamp exists to prevent, arriving through the one branch
    the missing-key check does not cover.
    """
    good = {"fixture_id": f"{SEASON_CODE}:arsenal:coventry",
            "date_played": "2026-08-21", "hg": 2, "ag": 0,
            "observed_at": "2026-08-22"}
    assert len(la.normalise_rows([good], manifest)) == 1          # control: valid

    for bad in (None, "", "not a timestamp", float("nan"), pd.NaT, np.nan):
        with pytest.raises(season_mod.SeasonError):
            la.normalise_rows([dict(good, observed_at=bad)], manifest)

    # A READY-MADE `LiveRow` GOES THROUGH THE SAME CHECKS AS A DICT.
    # A typed object is not a checked one: nothing stops `LiveRow` being
    # constructed with a `NaT` stamp or a negative score, and the old
    # `normalise_rows` waved such an object straight through on the strength of
    # its type. `NaT` compares False against every bound, so the row really was
    # visible at a cutoff years before it — the leak, arriving through the one
    # input shape the guard did not cover.
    def live_row(**over):
        base = dict(fixture_id=f"{SEASON_CODE}:arsenal:coventry",
                    home_key="arsenal", away_key="coventry",
                    date_played=pd.Timestamp("2026-08-21"),
                    observed_at=pd.Timestamp("2026-08-22"), hg=2, ag=0)
        return la.LiveRow(**{**base, **over})

    # POSITIVE CONTROL: the well-formed object still resolves, through both
    # doors, so the refusals below are refusals of the CONTENT.
    assert len(la.normalise_rows([live_row()], manifest)) == 1
    assert len(la.visible_rows([live_row()], "2026-08-25", "2026-08-30")) == 1

    for bad in (dict(observed_at=pd.NaT), dict(date_played=pd.NaT),
                dict(hg=-1), dict(ag=-1)):
        with pytest.raises(season_mod.SeasonError):
            la.normalise_rows([live_row(**bad)], manifest)
        with pytest.raises(season_mod.SeasonError):
            la.visible_rows([live_row(**bad)], "2026-08-25", "2026-08-30")

    # The `observed_at` stamp is the one thing read BEFORE the knowledge bound,
    # because it IS the bound: a `NaT` there would otherwise let the row through
    # at a cutoff six years earlier, which is precisely the leak.
    with pytest.raises(season_mod.SeasonError, match="observed_at"):
        la.visible_rows([live_row(observed_at=pd.NaT)], "2026-08-25", "2020-01-01")
    # ...while a row whose CONTENT is bad but which nobody has observed yet is
    # correctly invisible and silent — the append-only rule, not an oversight.
    assert la.visible_rows([live_row(hg=-1)], "2026-08-25", "2020-01-01") == ()

    # ...and the unknown club is caught on a `LiveRow` too, not only on a dict.
    with pytest.raises(la.TransitionError, match="not in the"):
        la.normalise_rows([live_row(fixture_id=f"{SEASON_CODE}:arsenal:luton",
                                    away_key="luton")], manifest)


def test_normalise_rows_refuses_a_date_played_that_is_not_a_timestamp(manifest):
    """The same hole, the same shape: `NaT >= day` is False, so the row is
    visible before it was played."""
    good = {"fixture_id": f"{SEASON_CODE}:arsenal:coventry",
            "date_played": "2026-08-21", "hg": 2, "ag": 0,
            "observed_at": "2026-08-22"}
    assert len(la.normalise_rows([good], manifest)) == 1          # control: valid
    for bad in (None, "", "not a timestamp", float("nan"), pd.NaT):
        with pytest.raises(season_mod.SeasonError):
            la.normalise_rows([dict(good, date_played=bad)], manifest)


def test_normalise_rows_enforces_fixture_identity(manifest, monkeypatch):
    """A ledger row must describe a fixture that exists, and describe it once.

    Both failures are hand-entry failures and neither is loud: a self-fixture
    walks a club against itself and moves its rating by a match that cannot have
    happened, and a `fixture_id` that disagrees with its own `home_key`/
    `away_key` silently attributes a result to the wrong pair of clubs. Nothing
    downstream re-derives either — the id is what the sim addresses fixtures by.

    The self-play cases are asserted with `epl.season.fixture_id` STUBBED
    PERMISSIVE. `fixture_id` refuses a self-fixture itself, so an assertion that
    merely raises `SeasonError` here passes whether or not `_check_identity`
    holds a guard of its own — it is the second line of defence answering for
    the first, which is a test that cannot fail. With the stub in place the
    refusal can only come from the guard under test.
    """
    good = {"fixture_id": f"{SEASON_CODE}:arsenal:coventry",
            "date_played": "2026-08-21", "hg": 2, "ag": 0,
            "observed_at": "2026-08-22"}

    with monkeypatch.context() as patch:
        patch.setattr(la, "fixture_id",
                      lambda code, home, away: f"{code}:{home}:{away}")
        # a club cannot play itself, whether the id says so...
        with pytest.raises(la.TransitionError, match="cannot play itself"):
            la.normalise_rows(
                [dict(good, fixture_id=f"{SEASON_CODE}:arsenal:arsenal")], manifest)
        # ...or the explicit team keys do
        with pytest.raises(la.TransitionError, match="cannot play itself"):
            la.normalise_rows([dict(good, fixture_id=None,
                                    home_key="arsenal", away_key="arsenal")], manifest)
        # POSITIVE CONTROL for the stub: under the same stub a legitimate row
        # still normalises, so the two refusals above are the guard firing and
        # not the stub breaking the call.
        under_stub = la.normalise_rows(
            [dict(good, fixture_id=None, home_key="arsenal", away_key="coventry")],
            manifest)
        assert under_stub[0].fixture_id == f"{SEASON_CODE}:arsenal:coventry"

    # an id that contradicts the teams beside it: home wrong...
    with pytest.raises(season_mod.SeasonError):
        la.normalise_rows([dict(good, home_key="chelsea", away_key="coventry")],
                          manifest)
    # ...and away wrong (a reversed pair is a REAL, separate fixture)
    with pytest.raises(season_mod.SeasonError):
        la.normalise_rows([dict(good, home_key="coventry", away_key="arsenal")],
                          manifest)

    # POSITIVE CONTROL: teams that agree with the id are accepted, and so is a
    # row that carries teams and no id at all.
    agreeing = la.normalise_rows(
        [dict(good, home_key="arsenal", away_key="coventry")], manifest)
    assert (agreeing[0].fixture_id, agreeing[0].home_key, agreeing[0].away_key) == (
        f"{SEASON_CODE}:arsenal:coventry", "arsenal", "coventry")
    from_teams = la.normalise_rows(
        [dict(good, fixture_id=None, home_key="arsenal", away_key="coventry")],
        manifest)
    assert from_teams[0].fixture_id == f"{SEASON_CODE}:arsenal:coventry"


def test_normalise_rows_skips_supported_statuses_and_refuses_the_rest(manifest):
    """A status the walk does not model must raise, exactly as `epl.season` does.

    Dropping every non-null status silently is the failure: an `awarded` result
    is out of v1 scope and `epl.season` stops the run on it, so an anchor that
    quietly walks past the same row prices a season the table refuses to score.
    The supported set is IMPORTED from `epl.season`, not restated here — two
    lists of statuses would drift, and the drift would be silent in this
    direction too.
    """
    assert la.LEDGER_STATUSES is season_mod._LEDGER_STATUSES     # one source of truth

    def status_row(status):
        return {"fixture_id": f"{SEASON_CODE}:arsenal:coventry", "status": status,
                "source": "manual", "observed_at": "2026-08-21T18:00", "note": ""}

    for status in sorted(la.LEDGER_STATUSES):                    # postponed, abandoned
        assert la.normalise_rows([status_row(status)], manifest) == ()

    for status in ("awarded", "void", "who knows"):
        with pytest.raises(season_mod.UnsupportedResultStatus):
            la.normalise_rows([status_row(status)], manifest)

    # POSITIVE CONTROL: a row with no status at all is still a result.
    assert len(la.normalise_rows([{
        "fixture_id": f"{SEASON_CODE}:arsenal:coventry", "date_played": "2026-08-21",
        "hg": 2, "ag": 0, "observed_at": "2026-08-22"}], manifest)) == 1


def test_a_later_status_unplays_a_score_in_the_walk_as_well_as_the_table(manifest):
    """ONE resolution: `abandoned` after a score is unplayed for BOTH readers.

    The walk used to drop every status row before resolving, so the score kept
    winning by default and the anchor walked a club's rating forward through a
    result the league had taken away — while `Season.at`, reading the same file,
    called the fixture unplayed. Two answers to one question, and the anchor's
    was the wrong one.

    Asserted against `Season.at` on the same ledger rather than against a
    hard-coded expectation, because agreement is the property, and in both
    directions: a postponement later corrected by the result of the rearranged
    match still resolves to the RESULT, so the fix is not "statuses win".
    """
    fid = f"{SEASON_CODE}:arsenal:coventry"
    score = {"fixture_id": fid, "date_played": "2026-08-21", "hg": 2, "ag": 0,
             "source": "manual", "observed_at": "2026-08-22T09:00", "note": ""}
    later_status = {"fixture_id": fid, "status": "abandoned", "source": "manual",
                    "observed_at": "2026-08-23T09:00", "note": "crowd trouble"}
    later_score = dict(score, observed_at="2026-08-24T09:00", hg=1, ag=1)

    def both(rows, cutoff="2026-08-25"):
        season = dataclasses.replace(
            season_mod.Season.load(SEASON), results=tuple(rows))
        walk = {r.fixture_id: (r.hg, r.ag)
                for r in la.normalise_rows(rows, manifest, cutoff=cutoff,
                                           observed_by=cutoff)}
        return season.at(cutoff).played, walk

    # POSITIVE CONTROL: the score alone is played for both readers.
    table, walk = both([score])
    assert table == {fid: (2, 0)} and walk == {fid: (2, 0)}

    # the defect: a later `abandoned` unplays it — in the table AND in the walk
    table, walk = both([score, later_status])
    assert table == {} and walk == {}

    # ...and the other direction still resolves to the result, so nothing here
    # privileges statuses over scores; the LATER OBSERVATION wins either way.
    table, walk = both([score, later_status, later_score])
    assert table == {fid: (1, 1)} and walk == {fid: (1, 1)}

    # ...and the abandonment is invisible before it was filed, so the walk is
    # reading a knowledge clock and not a rule about statuses.
    table, walk = both([score, later_status], cutoff="2026-08-22T18:00")
    assert table == {fid: (2, 0)} and walk == {fid: (2, 0)}


@needs_archive
def test_a_future_bad_row_does_not_break_an_earlier_forecast(manifest, cfg,
                                                             played):
    """A row filed tomorrow may not break a forecast issued yesterday.

    The results ledger is append-only: today's hand-entry error sits in the same
    file as every row before it. `LiveAnchor.__init__` used to normalise the
    WHOLE file eagerly — club membership, statuses, scores — so an unknown club
    or an `awarded` row filed in September made every August forecast
    unloadable, including a rerun of one already issued. Content is now read
    behind the known-at filter, exactly as `Season.at` reads it.

    Three shapes of bad row, each of them a real hand-entry failure, and each
    with its POSITIVE CONTROL: the same row DOES stop the walk the moment it is
    observed. A guard that never fires is not a guard.
    """
    good = {"fixture_id": f"{SEASON_CODE}:arsenal:coventry",
            "date_played": "2026-08-21", "hg": 2, "ag": 0,
            "source": "manual", "observed_at": "2026-08-22T09:00", "note": ""}
    future = "2026-09-30T12:00"
    bad_rows = {
        "unknown club": {"fixture_id": f"{SEASON_CODE}:arsenal:luton",
                         "date_played": "2026-09-20", "hg": 1, "ag": 0,
                         "source": "manual", "observed_at": future, "note": ""},
        "unsupported status": {"fixture_id": f"{SEASON_CODE}:chelsea:arsenal",
                               "status": "awarded", "source": "manual",
                               "observed_at": future, "note": ""},
        "bad score": {"fixture_id": f"{SEASON_CODE}:chelsea:arsenal",
                      "date_played": "2026-09-20", "hg": -1, "ag": 0,
                      "source": "manual", "observed_at": future, "note": ""},
    }
    teams = ["arsenal", "coventry"]

    for what, bad in bad_rows.items():
        ledger = [good, bad]
        # CONSTRUCTION does not read the ledger's content at all...
        anchor = la.LiveAnchor(played, ledger, manifest, cfg)
        # ...and the forecast that was issued before the bad row was filed is
        # still exactly the forecast it was, ledger row and all.
        state = anchor.state("2026-08-25", teams, observed_by="2026-08-25")
        clean = la.LiveAnchor(played, [good], manifest, cfg).state(
            "2026-08-25", teams, observed_by="2026-08-25")
        assert state.ratings == clean.ratings, what
        assert {r.fixture_id for r in anchor.visible_rows(
            "2026-08-25", "2026-08-25")} == {good["fixture_id"]}, what

        # POSITIVE CONTROL: once the row is observed, the walk fails closed.
        with pytest.raises(season_mod.SeasonError):
            anchor.state("2026-10-05", teams, observed_by="2026-10-05")


def test_partial_team_keys_are_checked_against_the_fixture_id(manifest):
    """One supplied key is checked, not silently overwritten from the id.

    `teams_given` was `home is not None and away is not None`, so a row
    carrying ONE key skipped the identity check and then had BOTH keys
    overwritten from the `fixture_id`. A row saying `home_key: "chelsea"` under
    `2627:arsenal:coventry` was therefore rated as Arsenal, quietly — the exact
    mis-attribution the identity check exists to stop, reached through the
    branch it did not cover.
    """
    good = {"fixture_id": f"{SEASON_CODE}:arsenal:coventry",
            "date_played": "2026-08-21", "hg": 2, "ag": 0,
            "observed_at": "2026-08-22"}

    # POSITIVE CONTROLS: an AGREEING partial key is accepted, from either side,
    # and the missing side is filled from the id.
    for partial in ({"home_key": "arsenal"}, {"away_key": "coventry"}):
        row = la.normalise_rows([dict(good, **partial)], manifest)[0]
        assert (row.home_key, row.away_key) == ("arsenal", "coventry")

    # a CONTRADICTING partial key, from either side, stops the walk
    for partial in ({"home_key": "chelsea"}, {"away_key": "chelsea"}):
        with pytest.raises(season_mod.SeasonError):
            la.normalise_rows([dict(good, **partial)], manifest)

    # ...and a partial key with no id at all cannot be resolved, so it refuses
    with pytest.raises(la.TransitionError, match="neither fixture_id nor"):
        la.normalise_rows([dict(good, fixture_id=None, home_key="arsenal")],
                          manifest)


@needs_archive
def test_visible_live_rows_match_season_state_played(manifest):
    """The anchor's point-in-time filter must agree with `Season.at`'s."""
    season = season_mod.Season.load(SEASON)
    ledger = [{"fixture_id": f.fixture_id,
               "date_played": str(f.base_date), "hg": 1, "ag": 0,
               "source": "test", "observed_at": str(f.base_date), "note": ""}
              for f in season.by_matchday(1)]
    live = dataclasses.replace(season, results=tuple(ledger))
    rows = la.normalise_rows(ledger, manifest)
    for cutoff in ("2026-08-21", "2026-08-23", "2026-08-25", "2026-09-01"):
        state = live.at(cutoff)
        got = {r.fixture_id for r in la.visible_rows(rows, cutoff, cutoff)}
        assert got == set(state.played), cutoff
    assert len(live.at("2026-09-01").played) == 10       # control: not empty


# ==========================================================================
# 3. the 2026/27 transition (P0-1)
# ==========================================================================
@needs_archive
def test_open_2026_27_seeds_coventry_hull_ipswich_at_division_mean_minus_75(
        played, manifest, cfg):
    arch = anchor_mod.Anchor(played, cfg)
    opening = la.open_target_season(arch, manifest, cfg)

    final = arch._final_ratings()
    mean = float(np.mean([final[c] for c in sorted(manifest.prev_season_clubs)]))
    seed = mean + cfg.promoted_offset
    assert mean == pytest.approx(DIVISION_MEAN_2627, abs=0.01)
    assert seed == pytest.approx(PROMOTED_SEED_2627, abs=0.01)

    assert set(manifest.promoted) == {"coventry", "hull", "ipswich"}
    for club in manifest.promoted:
        assert opening[club] == seed, club
    # POSITIVE CONTROL: this is a CHANGE for two of the three — the archive
    # really was handing out their stale ratings.
    assert final["hull"] == pytest.approx(HULL_STALE, abs=0.01)
    assert final["ipswich"] == pytest.approx(IPSWICH_STALE, abs=0.01)
    assert "coventry" not in final
    assert all(c in opening for c in manifest.clubs)


@needs_archive
def test_open_2026_27_leaves_wolves_burnley_west_ham_rated_but_outside_manifest(
        played, manifest, cfg):
    arch = anchor_mod.Anchor(played, cfg)
    final = arch._final_ratings()
    opening = la.open_target_season(arch, manifest, cfg)

    for club in ("burnley", "west_ham", "wolves"):
        assert club in manifest.relegated
        assert club not in manifest.clubs
        assert club in opening                       # still rated...
        assert opening[club] == final[club]          # ...and untouched
    # carryover == 1.0, so a continuing club keeps its rating to the last bit
    # of rounding; assert the shape rather than the identity.
    assert opening["arsenal"] == pytest.approx(final["arsenal"], abs=1e-9)

    # THE ASSERTIONS ABOVE CANNOT FAIL ON THEIR OWN. Every one of them holds if
    # `open_target_season` simply handed back `_final_ratings()` — a relegated
    # club's rating is untouched there too, and carryover is 1.0 for a
    # continuing club. What must differ is the promoted half, so it is pinned
    # here: each promoted club enters at the reseed, NOT at whatever the archive
    # last had for it (Hull's 2016/17 rating, Ipswich's relegated season, and
    # for Coventry no rating at all).
    seed = float(np.mean([final[c] for c in sorted(manifest.prev_season_clubs)])) \
        + cfg.promoted_offset
    assert seed == pytest.approx(PROMOTED_SEED_2627, abs=0.01)
    assert set(manifest.promoted) == {"coventry", "hull", "ipswich"}
    for club in manifest.promoted:
        assert opening[club] == seed, club
    assert "coventry" not in final
    assert final["hull"] == pytest.approx(HULL_STALE, abs=0.01)
    assert final["ipswich"] == pytest.approx(IPSWICH_STALE, abs=0.01)
    assert abs(opening["hull"] - final["hull"]) > 100.0
    assert abs(opening["ipswich"] - final["ipswich"]) > 100.0


@needs_archive
def test_state_before_first_result_returns_transitioned_table_not_final_ratings(
        played, manifest, cfg):
    live = la.LiveAnchor(played, [], manifest, cfg)
    teams = sorted(set(played["home_key"]) | set(played["away_key"]))
    state = live.state(OPENER, teams)

    assert state.ratings["hull"] == pytest.approx(PROMOTED_SEED_2627, abs=0.01)
    assert state.ratings["hull"] != pytest.approx(HULL_STALE, abs=0.01)
    assert state.ratings["ipswich"] == state.ratings["hull"]
    assert state.ratings["coventry"] == state.ratings["hull"]
    assert np.isfinite(state.z("coventry"))

    # POSITIVE CONTROL: the un-transitioned anchor exhibits the P0-1 bug.
    stale = anchor_mod.Anchor(played, cfg).state(OPENER, teams)
    assert stale.ratings["hull"] == pytest.approx(HULL_STALE, abs=0.01)
    with pytest.raises(KeyError):
        stale.z("coventry")


@needs_archive
def test_partial_season_walk_uses_manifest_club_set_not_rows(
        played, manifest, cfg):
    season = season_mod.Season.load(SEASON)
    opener = season.fixture(f"{SEASON_CODE}:arsenal:coventry")
    rows = [{"fixture_id": opener.fixture_id, "date_played": "2026-08-21",
             "hg": 2, "ag": 0, "source": "test",
             "observed_at": "2026-08-21", "note": ""}]
    live = la.LiveAnchor(played, rows, manifest, cfg)
    teams = sorted(set(played["home_key"]) | set(played["away_key"]))
    state = live.state("2026-08-22", teams)
    opening = live.opening_table()

    # only two clubs appear in the rows; all twenty must be seeded
    assert {"arsenal", "coventry"} == {opener.home_key, opener.away_key}
    for club in manifest.clubs:
        assert club in state.ratings, club
    untouched = [c for c in manifest.clubs if c not in ("arsenal", "coventry")]
    assert len(untouched) == 18
    for club in untouched:
        assert state.ratings[club] == opening[club], club
    assert state.ratings["hull"] == pytest.approx(PROMOTED_SEED_2627, abs=0.01)

    # the two that played moved, in the right direction (2-0 home win)
    assert state.ratings["arsenal"] > opening["arsenal"]
    assert state.ratings["coventry"] < opening["coventry"]
    # and before the result's day they had not moved (positive control on the
    # cutoff, not just on the club set)
    before = live.state(OPENER, teams)
    assert before.ratings["arsenal"] == opening["arsenal"]


@needs_archive
def test_state_cache_does_not_confuse_two_known_at_bounds(played, manifest, cfg):
    """Two cutoffs on the SAME DAY with different known-at bounds must differ.

    The walk is memoised per cutoff, and a cache keyed on the day alone would
    serve the later call's answer to the earlier one — showing a result before
    it was observed. This is the guard on that key.
    """
    rows = [{"fixture_id": f"{SEASON_CODE}:arsenal:coventry",
             "date_played": "2026-08-21", "hg": 2, "ag": 0, "source": "test",
             "observed_at": "2026-08-25 14:00", "note": ""}]
    live = la.LiveAnchor(played, rows, manifest, cfg)
    teams = sorted(set(played["home_key"]) | set(played["away_key"]))
    opening = live.opening_table()

    early = live.state("2026-08-25 09:00", teams)       # before it was observed
    late = live.state("2026-08-25 20:00", teams)        # after
    assert early.ratings["arsenal"] == opening["arsenal"]
    assert late.ratings["arsenal"] > opening["arsenal"]
    # and again, from the cache, in the other order
    assert live.state("2026-08-25 09:00", teams).ratings["arsenal"] == \
        opening["arsenal"]


@needs_archive
def test_cold_start_for_returns_only_coventry_at_opener(played, manifest, cfg):
    live = la.LiveAnchor(played, [], manifest, cfg)
    archive_clubs = sorted(set(played["home_key"]) | set(played["away_key"]))
    assert live.cold_start_for(archive_clubs) == ["coventry"]
    # positive control: drop a club the archive HAS and it must be reported too
    assert live.cold_start_for([c for c in archive_clubs if c != "hull"]) == [
        "coventry", "hull"]


# ==========================================================================
# 4. the parity that licenses the duplicated update loop
# ==========================================================================
@needs_archive
def test_explicit_replay_of_2025_26_matches_anchor_snapshots_bitwise(played, cfg):
    full = anchor_mod.Anchor(played, cfg)
    prior = sort_for_walk_forward(played.loc[played["season"] != PREV_SEASON])
    part = anchor_mod.Anchor(prior, cfg)
    mf = _synthetic_manifest(played, PREV_SEASON, "2024/25")

    ratings = la.open_target_season(part, mf, cfg)
    target = sort_for_walk_forward(played.loc[played["season"] == PREV_SEASON])
    res = la.replay(ratings, target, cfg, promoted=mf.promoted)

    want = [s for s in full._snapshots if s["season"] == PREV_SEASON]
    assert len(res.snapshots) == len(want) > 100
    for got, exp in zip(res.snapshots, want):
        assert pd.Timestamp(got["key"]) == pd.Timestamp(exp["key"])
        assert set(got["ratings"]) == set(exp["ratings"])
        for club, value in exp["ratings"].items():
            assert float(got["ratings"][club]) == float(value), club

    # POSITIVE CONTROL: one point of K must break the bitwise comparison.
    bad = cfg.replace(k=cfg.k + 1.0)
    off = la.replay(la.open_target_season(part, mf, bad), target, bad,
                    promoted=mf.promoted)
    assert any(float(off.snapshots[-1]["ratings"][c]) != float(v)
               for c, v in want[-1]["ratings"].items())


@needs_archive
def test_live_anchor_replaying_2025_26_matches_archive_state_at_every_cutoff(
        played, cfg):
    """End-to-end: `LiveAnchor` over 2025/26-as-live == `Anchor` over the archive.

    This is the parity that licenses the live path, not just the loop: the live
    walk blocks by DAY (a ledger has no kickoff times) where the archive blocks
    by KICKOFF, and the two must still agree, because a club's rating moves only
    in its own matches and no club plays twice in a day.
    """
    prior = sort_for_walk_forward(played.loc[played["season"] != PREV_SEASON])
    target = sort_for_walk_forward(played.loc[played["season"] == PREV_SEASON])
    mf = _synthetic_manifest(played, PREV_SEASON, "2024/25")
    live = la.LiveAnchor(prior, _live_rows_from_frame(target, "2526"), mf, cfg)
    arch = anchor_mod.Anchor(played, cfg)
    teams = sorted(set(prior["home_key"]) | set(prior["away_key"]))

    checked = 0
    for cutoff in ("2025-09-01", "2025-11-01", "2026-01-15", "2026-03-01",
                   "2026-05-01", "2026-05-25"):
        a = arch.state(cutoff, teams).ratings
        b = live.state(cutoff, teams).ratings
        for club in sorted(set(a)):
            assert float(b[club]) == float(a[club]), (cutoff, club)
        checked += 1
    assert checked == 6
    # POSITIVE CONTROL: the ratings actually move across those cutoffs, so the
    # equality above is not comparing two frozen tables.
    assert (arch.state("2025-09-01", teams).ratings["arsenal"]
            != arch.state("2026-05-01", teams).ratings["arsenal"])


@needs_archive
def test_history_frame_extends_the_archive_with_live_rows(played, cfg):
    prior = sort_for_walk_forward(played.loc[played["season"] != PREV_SEASON])
    target = sort_for_walk_forward(played.loc[played["season"] == PREV_SEASON])
    mf = _synthetic_manifest(played, PREV_SEASON, "2024/25")
    live = la.LiveAnchor(prior, _live_rows_from_frame(target, "2526"), mf, cfg)

    hist = live.history_frame()
    arch = anchor_mod.Anchor(prior, cfg).history
    assert list(hist.columns) == list(arch.columns)
    assert len(hist) == len(arch) + len(target)
    tail = hist.loc[hist["season"] == PREV_SEASON]
    assert len(tail) == 380
    assert set(tail["ftr"]) <= {"H", "D", "A"}
    assert np.isfinite(tail["elo_diff_pre"].to_numpy(float)).all()
    assert tail["block"].min() > arch["block"].max()
    # point-in-time: a live row's pre-rating equals the anchor's state on its day
    row = tail.iloc[100]
    state = live.state(pd.Timestamp(row["date"]), [row["home_key"]])
    assert float(state.ratings[row["home_key"]]) == float(row["elo_home_pre"])


# ==========================================================================
# 5. the real fit at the opener
# ==========================================================================
@needs_archive
@pytest.mark.slow
def test_fit_epl_at_opener_prices_every_fixture_incl_coventry(
        played, manifest, cfg, capsys):
    import time

    from wcmodel.data import features as wc_features

    from epl import dcfit, fit as epl_fit
    from epl.dcfit import to_match_panel

    wcfg = freeze.frozen_wcmodel_config()
    store = epl_fit.build_store(played)
    live = la.LiveAnchor(played, [], manifest, cfg)
    season = season_mod.Season.load(SEASON)

    t0 = time.perf_counter()
    with epl_fit.config_read_once(wcfg):
        panel = to_match_panel(wc_features.build_cached(
            OPENER, store, wcfg, cache_dir=paths.FIT_CACHE_DIR))
        fitted = sorted(set(panel["home_team"]) | set(panel["away_team"]))
        cold = live.cold_start_for(fitted)
        assert cold == ["coventry"]
        post, res = dcfit.fit_epl(OPENER, store, live, wcfg, cold_start=cold,
                                  feature_cache_dir=paths.FIT_CACHE_DIR)
    seconds = time.perf_counter() - t0

    for club in manifest.clubs:
        assert club in post._idx, club
    assert res.cold_start_teams == ["coventry"]
    for fixture in season.by_matchday(1):
        p = post.predict_1x2(fixture.home_key, fixture.away_key, neutral=False)
        vals = [float(p[k]) for k in score_mod.OUTCOMES]
        assert all(np.isfinite(v) for v in vals), fixture.fixture_id
        assert abs(sum(vals) - 1.0) < 1e-9, fixture.fixture_id
    assert len(season.by_matchday(1)) == 10
    with capsys.disabled():
        print(f"\n[T2] fit at {OPENER}: {seconds:.1f}s "
              f"({res.n_training_matches} training matches, "
              f"{res.n_teams} fitted teams)")
