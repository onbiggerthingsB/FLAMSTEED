"""A12 — `dc_1x2_avail`: the availability shadow arm, a fixed prior not a fit.

    PYTHONPATH=src:. .venv/bin/pytest epl/tests/test_availarm.py -q

WHAT THIS SUITE HOLDS THE CODE TO. A12 (``reports/epl_sim_amendments.md``)
freezes a RULE whose every constant is stated in the entry: `k_avail = 1.0`, a
PRIOR from the injury-cost literature and not a fit; the status ladder with its
null default of 0.5; the 2970-minute switchover, which is `3 x 990` and an
arithmetic identity rather than a tuned number; and the tilt itself, which
moves the home-vs-away log-odds of the PUBLISHED marginals by exactly `d` nats
and leaves the draw's log-strength alone.

So the arithmetic tests here are hand-computed against the entry, not against
this implementation's own output: the two controls A12 pre-states (the evens
fixture and the pinned Arsenal-Coventry snapshot) are written as literals, and
a test that merely re-ran the code would be a test of nothing.

CI-SAFE. Everything except the two guarded controls runs on synthetic payloads
and `tmp_path`: no network, no `data/`, no wall clock.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import numpy as np
import pytest

from epl import availability as av, availarm, matchboard, season as season_mod

REPO_ROOT = Path(availarm.__file__).resolve().parents[1]
AMENDMENTS = REPO_ROOT / "reports" / "epl_sim_amendments.md"

#: The one real snapshot A12's worked control is computed from. Present on the
#: machine that pulled it and nowhere else, so the control that reads it is
#: guarded exactly like the pinned-corpus tests in `test_recal.py`.
PINNED_SNAPSHOT = (REPO_ROOT / "data" / "epl" / "availability" / "raw"
                   / "bootstrap_20260827T023039Z.json.gz")

#: The committed shadow ledger, once a matchweek has filed into it.
AVAIL_LEDGER = REPO_ROOT / "reports" / "epl_avail_shadow.jsonl"


# ==========================================================================
# helpers — a synthetic season, a synthetic board, a synthetic archive
# ==========================================================================

SEASON_IDS = ("2627:alpha:bravo", "2627:charlie:delta", "2627:echo:foxtrot",
              "2627:golf:hotel", "2627:india:juliet")
FACTS = {
    "2627:alpha:bravo": {"home": "alpha", "away": "bravo", "date": "2026-08-21"},
    "2627:charlie:delta": {"home": "charlie", "away": "delta",
                           "date": "2026-08-22"},
    "2627:echo:foxtrot": {"home": "echo", "away": "foxtrot",
                          "date": "2026-08-23"},
    "2627:golf:hotel": {"home": "golf", "away": "hotel", "date": "2026-08-24"},
    "2627:india:juliet": {"home": "india", "away": "juliet",
                          "date": "2026-08-25"},
}


def _spread_rows() -> dict:
    """Four particles that disagree, so the marginals are not degenerate."""
    per = 250
    particle = np.repeat(np.arange(4, dtype=np.int16), per)
    scorelines = np.zeros((4 * per, 1, 2), np.int8)
    scorelines[0 * per:1 * per] = (4, 0)
    scorelines[1 * per:2 * per] = (1, 1)
    scorelines[2 * per:3 * per] = (0, 1)
    scorelines[3 * per:3 * per + per // 2] = (2, 0)
    scorelines[3 * per + per // 2:4 * per] = (0, 2)
    return {"scorelines": scorelines, "particle": particle,
            "fixture_ordinals": np.asarray([0], np.int32)}


def _board(rows=None, **overrides) -> dict:
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS) if rows is None else rows
    doc = {
        "schema_version": matchboard.SCHEMA_VERSION,
        "season": "2026/27", "arm": "dc_native",
        "cutoff": "2026-08-21 00:00:00", "observed_by": "2026-08-21 00:00:00",
        "seed": 20260611, "chunk_size": 2000, "n_sims": int(rows[0]["n_sims"]),
        "n_particles": int(rows[0]["n_particles"]), "n_fixtures": len(rows),
        "source_rows": "rows_dc_native.npz",
        "effective_posterior_hash": "b8" * 32, "run_digest": "3a" * 32,
        "manifest_sha256": "01" * 32, "fixtures_base_sha256": "02" * 32,
        "kickoff_amendments_sha256": "03" * 32,
        "max_goals": 10, "n_provisional": 38, "rows_provenance": "reproduction",
        "source_bundle": "data/epl/sim/issuances/2026_27/2026-08-21",
        "rows": rows,
    }
    doc.update(overrides)
    return doc


def _board_for(fixture_id: str, **overrides) -> dict:
    """A board carrying ONE named fixture.

    `_board()`'s particle block declares a single fixture ordinal, so its row is
    always `SEASON_IDS[0]`; a test that wants a second key in the ledger — a
    second FIXTURE rather than a second issuance — has to price a different one,
    and a result the board never priced is refused by the matchboard long before
    this arm sees it.
    """
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=(fixture_id,),
                                  facts=FACTS)
    return _board(rows, **overrides)


def _ledger(*rows):
    return season_mod.resolve_ledger(
        [{"observed_at": "2026-08-22T09:00:00",
          "date_played": FACTS[row["fixture_id"]]["date"], **row}
         for row in rows],
        identify=lambda row: str(row["fixture_id"]))


def _played(fixture_id="2627:alpha:bravo", hg=2, ag=0, **extra):
    return {"fixture_id": fixture_id, "hg": hg, "ag": ag, **extra}


def _result(fixture_id="2627:alpha:bravo", hg=2, ag=0, mw=1,
            ingest="manual/test"):
    return {"fixture_id": fixture_id, "home_goals": hg, "away_goals": ag,
            "matchweek": mw, "ingest": ingest}


def _p(pid: int, *, status: str = "a", chance=None, minutes: int = 0,
       now_cost: int = 50, web_name: str | None = None,
       team_key: str = "alpha", news: str = "", news_added=None) -> dict:
    """One player as :func:`epl.availability.as_of` hands it over."""
    return {"player_id": pid,
            "web_name": web_name if web_name is not None else f"P{pid}",
            "team_key": team_key, "status": status, "chance_next": chance,
            "news": news, "news_added": news_added, "minutes": minutes,
            "now_cost": now_cost}


def _squad(n: int, *, team_key: str, minutes: int = 0, now_cost: int = 50,
           first: int = 1) -> list[dict]:
    return [_p(first + i, team_key=team_key, minutes=minutes,
               now_cost=now_cost) for i in range(n)]


#: PIT-CLEAN BY DEFAULT. `_board()`'s knowledge clock is 2026-08-21 00:00:00,
#: so the default synthetic view is observed the day BEFORE it. The committed
#: r6 suite defaulted to the real 2026-08-27 pull — six days after the board it
#: priced — and every scoring test in it was therefore exercising the side door
#: A12 (b) never authorised. A view observed after the clock is now a case a
#: test has to ASK for, and section 10 asks for it.
def _view(squads: dict[str, list[dict]], *, stamp: str = "20260820T090000Z",
          observed_at: str = "2026-08-20T09:00:00Z",
          sha256: str = "ce" * 32) -> av.AsOfSnapshot:
    return av.AsOfSnapshot(
        stamp=stamp, observed_at=observed_at, sha256=sha256,
        raw_path=Path(f"bootstrap_{stamp}.json.gz"),
        n_players=sum(len(v) for v in squads.values()),
        line={"stamp": stamp, "observed_at": observed_at, "sha256": sha256,
              "raw": f"bootstrap_{stamp}.json.gz"},
        squads={k: tuple(v) for k, v in squads.items()})


def _even_view(home_out: bool = True) -> av.AsOfSnapshot:
    """Eleven ever-present players a side, one of the home side's fully out.

    Eleven at 270 minutes is 2970 exactly — `3 x 990`, the switchover — so this
    is on the MINUTES branch and each player's share is exactly `1/11`.
    """
    home = _squad(11, team_key="alpha", minutes=270)
    away = _squad(11, team_key="bravo", minutes=270, first=101)
    if home_out:
        home[0] = {**home[0], "status": "i"}
    return _view({"alpha": home, "bravo": away})


def _rows(view=None, board=None, results=None, **kw):
    board = _board() if board is None else board
    results = [_result()] if results is None else results
    return availarm.score(
        board, results, snapshot=view,
        ledger=_ledger(*[_played(r["fixture_id"], r["home_goals"],
                                 r["away_goals"]) for r in results]), **kw)


def _one(view=None, **kw):
    return _rows(view if view is not None else _even_view(), **kw)[0]


# ==========================================================================
# 1. the fixed rule — A12 (b), hand-computed
# ==========================================================================

def test_the_status_ladder_is_the_one_A12_tabulates():
    """Every rung of A12 (b)'s table, including the two it rules for edges it
    has never seen: `n` (zero rows in the only real snapshot) and a `d` with a
    null chance (likewise zero)."""
    assert availarm.unavailability(_p(1, status="a")) == 0.0
    assert availarm.unavailability(_p(1, status="i")) == 1.0
    assert availarm.unavailability(_p(1, status="s")) == 1.0
    assert availarm.unavailability(_p(1, status="d", chance=75)) == 0.25
    assert availarm.unavailability(_p(1, status="d", chance=25)) == 0.75
    assert availarm.unavailability(_p(1, status="d", chance=0)) == 1.0
    assert availarm.unavailability(_p(1, status="d", chance=100)) == 0.0
    # excluded — a non-member, not an absence
    assert availarm.unavailability(_p(1, status="u")) is None
    assert availarm.unavailability(_p(1, status="n")) is None


def test_the_chance_field_is_deliberately_ignored_on_i_and_s():
    """A12 (b) states the cost of this simplification rather than hiding it:
    an injured player with a nonzero chance is overstated at a flat 1.0, and
    sharpening it is a new amendment rather than an implementation detail."""
    assert availarm.unavailability(_p(1, status="i", chance=75)) == 1.0
    assert availarm.unavailability(_p(1, status="s", chance=50)) == 1.0


def test_a_null_chance_on_a_doubt_defaults_to_the_ladders_middle_rung():
    """FPL's ladder is 25/50/75 and a null is the source DECLINING to guess;
    either extreme rung would import a direction the source did not give."""
    assert availarm.unavailability(_p(1, status="d", chance=None)) == 0.5
    assert availarm.NULL_CHANCE == 50.0
    assert availarm.NULL_CHANCE_UNAVAIL == 0.5


def test_an_unruled_status_is_a_typed_refusal_naming_the_player_and_the_code():
    """Never a silent skip: a code this rule has no rung for is a rule that
    would narrow itself the week the feed invents one."""
    with pytest.raises(availarm.StatusUnruled, match="'x'"):
        availarm.unavailability(_p(7, status="x", web_name="Ghost"))
    with pytest.raises(availarm.StatusUnruled, match="Ghost"):
        availarm.unavailability(_p(7, status="x", web_name="Ghost"))


def test_u_and_n_leave_the_squad_and_its_denominator_entirely():
    """A12 (b): "removed from the squad and its denominator entirely — not an
    absence, a non-member". The discrimination that matters: an excluded player
    must not dilute the shares of the players who remain."""
    two = availarm.side_feature([_p(1, status="i", now_cost=50),
                                 _p(2, now_cost=50)])
    with_loanee = availarm.side_feature([_p(1, status="i", now_cost=50),
                                         _p(2, now_cost=50),
                                         _p(3, status="n", now_cost=50),
                                         _p(4, status="u", now_cost=50)])
    assert two.n_included == 2 and with_loanee.n_included == 2
    assert two.denominator == with_loanee.denominator == 100
    assert two.feat == with_loanee.feat == 0.5, (
        "an excluded player in the denominator would have made this 0.25")


def test_the_minutes_switchover_is_the_arithmetic_identity_and_is_inclusive():
    """2970 = 3 x 990: three matches of eleven ninety-minute slots. AT the
    switchover the minutes branch is live — "if the club's summed minutes is
    >= 2970" — and one minute below it the price share carries the weight."""
    assert availarm.MINUTES_SWITCHOVER == 2970 == 3 * 990

    at = availarm.side_feature(_squad(11, team_key="alpha", minutes=270))
    assert at.weight_basis == availarm.WEIGHT_BASIS_MINUTES
    assert at.denominator == 2970

    players = _squad(11, team_key="alpha", minutes=270)
    players[0] = {**players[0], "minutes": 269}
    below = availarm.side_feature(players)
    assert below.weight_basis == availarm.WEIGHT_BASIS_FALLBACK
    assert below.denominator == 11 * 50


def test_below_the_switchover_the_weight_is_the_price_share():
    """The deviation A12 records once, in the entry, rather than letting an
    implementation quietly substitute something: the payload carries NO
    prior-season minutes, so the design sketch's "prior+current minutes" is not
    available and `now_cost` — the source's own standing summary of expected
    involvement — carries the weighting until three matches have been played."""
    out = availarm.side_feature([_p(1, status="i", now_cost=90, minutes=90),
                                 _p(2, now_cost=60, minutes=90),
                                 _p(3, now_cost=50, minutes=0)])
    assert out.weight_basis == availarm.WEIGHT_BASIS_FALLBACK
    assert out.denominator == 200
    assert out.feat == 90 / 200


def test_an_empty_squad_or_a_zero_denominator_is_refused_never_a_zero_feature():
    """A12 (b): "Empty squad or zero denominator = SquadEmpty refusal, never a
    zero feature." A zero feature means "everyone is fit", which is the exact
    opposite of "we know nothing about this club"."""
    with pytest.raises(availarm.SquadEmpty, match="no included players"):
        availarm.side_feature([])
    with pytest.raises(availarm.SquadEmpty):
        availarm.side_feature([_p(1, status="u"), _p(2, status="n")])
    with pytest.raises(availarm.SquadEmpty, match="denominator"):
        availarm.side_feature([_p(1, now_cost=0), _p(2, now_cost=0)])


def test_the_feature_is_the_weighted_unavailable_fraction_in_the_unit_interval():
    everyone_out = availarm.side_feature(
        [_p(i, status="i", now_cost=50) for i in range(1, 12)])
    assert everyone_out.feat == 1.0
    assert availarm.side_feature(_squad(11, team_key="alpha")).feat == 0.0


def test_the_tilt_moves_the_home_away_log_odds_by_exactly_d_nats():
    """A12 (b)'s whole content, as the identity it states:
    `log(q_home / q_away) = log(p_home / p_away) - d`, with the draw cell's
    log-strength untouched and moving only through renormalisation."""
    p = {"home": 0.55, "draw": 0.25, "away": 0.20}
    d = 0.3
    q = availarm.tilt(p, d)
    assert abs((np.log(q["home"] / q["away"])
                - np.log(p["home"] / p["away"])) + d) < 1e-12
    # the draw is carried through the SAME normaliser as the other two cells
    z = p["draw"] / q["draw"]
    assert abs(q["home"] * z - p["home"] * np.exp(-d / 2)) < 1e-15
    assert abs(q["away"] * z - p["away"] * np.exp(d / 2)) < 1e-15
    assert abs(sum(q.values()) - 1.0) <= availarm.SUM_TOLERANCE


def test_a_zero_tilt_is_the_identity():
    p = {"home": 0.4, "draw": 0.2, "away": 0.4}
    assert availarm.tilt(p, 0.0) == pytest.approx(p, abs=1e-15)
    assert availarm.adjust(p, 0.3, 0.3, k_avail=1.0) == pytest.approx(p, abs=1e-15)


def test_the_evens_control_is_A12_item_3_to_the_digit():
    """A12 item 3, pre-stated before any code existed: one ever-present player
    (minutes share 1/11) fully unavailable, at an evens fixture 0.4/0.2/0.4,
    moves the home cell to 0.381909532447 — a shift of -0.018090467553. That is
    the arithmetic placing `k_avail = 1.0` inside the literature's low
    single-digit-pp band, and it is a property of the FORMULA."""
    q = availarm.adjust({"home": 0.4, "draw": 0.2, "away": 0.4},
                        1.0 / 11.0, 0.0, k_avail=availarm.K_AVAIL)
    assert q["home"] == pytest.approx(0.381909532447, abs=5e-13)
    assert q["home"] - 0.4 == pytest.approx(-0.018090467553, abs=5e-13)


def test_the_evens_control_is_reached_through_the_squad_rule_too():
    """The same number, but computed from a SQUAD rather than from a feature
    handed in by hand — so the minutes branch, the share and the tilt are held
    to the pre-stated literal together."""
    view = _even_view()
    home = availarm.side_feature(view.squad("alpha"))
    away = availarm.side_feature(view.squad("bravo"))
    assert home.weight_basis == availarm.WEIGHT_BASIS_MINUTES
    assert home.feat == pytest.approx(1.0 / 11.0, abs=1e-15)
    assert away.feat == 0.0
    q = availarm.adjust({"home": 0.4, "draw": 0.2, "away": 0.4},
                        home.feat, away.feat)
    assert q["home"] == pytest.approx(0.381909532447, abs=5e-13)


def test_the_coefficient_is_a_prior_and_the_module_says_so_in_those_words():
    """A12: "`k_avail` is a PRIOR, not a fit, and this entry says so in exactly
    those words." No drift trigger, no refit schedule, and — unlike A8's annual
    constant — nothing in-season that moves it."""
    assert availarm.K_AVAIL == 1.0
    text = Path(availarm.__file__).read_text(encoding="utf-8")
    assert "a PRIOR, not a fit" in text
    for banned in ("def fit", "def refit", "minimize(", "curve_fit"):
        assert banned not in text, (
            f"{banned!r} in an arm A12 gives zero fitted parameters")


@pytest.mark.skipif(not PINNED_SNAPSHOT.exists(),
                    reason="the pinned availability snapshot is not on this machine")
def test_the_arsenal_coventry_control_is_the_pre_stated_vector():
    """A12 item 2's worked control, from the pinned snapshot and the published
    MW0 marginals A8 item 3 pins. Deliberately IMPOSSIBLE TO FILE — the fixture
    kicked off twelve days before the snapshot was observed — which is exactly
    what makes it safe as a control: it can check an implementation and can
    never become a score.

    Asserted to 1e-9 or better on the file's own values, never on a rendered
    four-decimal string (A8 item 4's rounding rule, carried over verbatim).
    """
    view = av.as_of("2026-08-27T12:00:00Z")
    arsenal = availarm.side_feature(view.squad("arsenal"))
    coventry = availarm.side_feature(view.squad("coventry"))

    assert view.line["n_players"] == 614
    assert arsenal.n_included == 29 and arsenal.denominator == 1793
    assert coventry.n_included == 31 and coventry.denominator == 1445
    assert arsenal.weight_basis == coventry.weight_basis \
        == availarm.WEIGHT_BASIS_FALLBACK, (
        "every club's summed minutes is under 2970 at this snapshot (max 988), "
        "so the now_cost branch is the live one for all twenty")
    assert arsenal.feat == pytest.approx(0.079475738985, abs=1e-12)
    assert coventry.feat == pytest.approx(0.038062283737, abs=1e-12)

    published = {"home": 0.763900, "draw": 0.161750, "away": 0.074350}
    q = availarm.adjust(published, arsenal.feat, coventry.feat)
    assert q["home"] == pytest.approx(0.758945627187, abs=1e-11)
    assert q["draw"] == pytest.approx(0.164063230911, abs=1e-11)
    assert q["away"] == pytest.approx(0.076991141902, abs=1e-11)
    assert q["home"] - published["home"] == pytest.approx(-0.004954372813,
                                                          abs=1e-11)


@pytest.mark.skipif(not PINNED_SNAPSHOT.exists(),
                    reason="the pinned availability snapshot is not on this machine")
def test_the_pinned_snapshot_is_the_alphabet_A12_observed():
    """The observation A12 records, re-counted: `a` 493, `i` 57, `u` 42, `d` 21,
    `s` 1, and `n` ZERO — the code the rule covers anyway."""
    view = av.as_of("2026-08-27T12:00:00Z")
    counts: dict[str, int] = {}
    nulls = 0
    for rows in view.squads.values():
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
            if row["status"] == "d" and row["chance_next"] is None:
                nulls += 1
    assert counts == {"a": 493, "i": 57, "u": 42, "d": 21, "s": 1}
    assert nulls == 0, (
        "A12 records that zero observed `d` rows carry null, which is what "
        "makes the 0.5 default a rule for an edge that does not exist yet")


# ==========================================================================
# 2. the rows — A12 (d)
# ==========================================================================

def test_a_scored_row_carries_every_field_A12_names_and_nothing_else():
    row = _one()
    assert tuple(row) == availarm.ROW_FIELDS
    assert row["schema_version"] == availarm.SCHEMA_VERSION \
        == "epl-avail-shadow-1"
    assert row["arm"] == availarm.ARM == "dc_1x2_avail"
    assert row["rule_version"] == availarm.RULE_VERSION == "dc-1x2-avail-1"
    assert row["k_avail"] == availarm.K_AVAIL == 1.0
    assert row["snapshot_stamp"] == "20260820T090000Z"
    assert row["snapshot_sha256"] == "ce" * 32
    assert row["weight_basis_home"] == row["weight_basis_away"] == "minutes"
    # A7 (f), carried onto this surface too: no benchmark comparison column
    assert not any("benchmark" in k for k in row)
    # and no market vocabulary anywhere on it
    text = json.dumps(row).lower()
    for banned in ("market", "vig", "odds", "devig", "bookmaker", "closing"):
        assert banned not in text


def test_probs_raw_is_the_published_marginal_copied_and_never_re_priced():
    board = _board()
    row = _one(board=board)
    published = board["rows"][0]["probs"]
    assert row["probs_raw"] == published
    for key in matchboard.OUTCOMES:
        assert row["probs_raw"][key] == published[key]      # the same double
    assert row["probs_avail"] == availarm.adjust(
        published, row["feat_home"], row["feat_away"], k_avail=row["k_avail"])
    assert abs(sum(row["probs_avail"].values()) - 1.0) <= availarm.SUM_TOLERANCE


def test_rps_raw_is_the_same_number_the_A7_scorecard_publishes():
    """The identity A8 item 6 pre-states for the recal arm, holding here for
    the same reason: `probs_raw` is COPIED, and both surfaces score it against
    the same outcome through :func:`epl.matchboard.rps`."""
    board = _board()
    ledger = _ledger(_played())
    card = matchboard.score(board, [_result()], ledger=ledger)[0]
    row = availarm.score(board, [_result()], snapshot=_even_view(),
                         ledger=ledger)[0]
    assert row["rps_raw"] == card["rps"]                    # the same double
    assert row["rps_uniform"] == card["rps_uniform"]
    assert row["outcome"] == card["outcome"] == "home"
    assert row["matchweek"] == 1 and row["ingest"] == "manual/test"


def test_the_uniform_column_is_the_two_pre_stated_literals():
    home = _one()
    draw = _rows(_even_view(), results=[_result(hg=1, ag=1)])[0]
    assert home["rps_uniform"] == 5 / 18
    assert draw["rps_uniform"] == 1 / 9
    assert draw["outcome"] == "draw"


def test_the_weight_basis_is_recorded_per_side_so_the_switchover_is_auditable():
    """A12 (b): "The branch taken is recorded on every row (`weight_basis`, per
    side)" — so which branch a number came from is read off the ledger rather
    than inferred from a snapshot somebody has to go and find."""
    view = _view({"alpha": _squad(11, team_key="alpha", minutes=270),
                  "bravo": _squad(11, team_key="bravo", minutes=100,
                                  first=101)})
    row = _one(view)
    assert row["weight_basis_home"] == "minutes"
    assert row["weight_basis_away"] == "now_cost"


def test_a_forecast_that_did_not_precede_the_kickoff_is_refused_by_name():
    """A7 (e), restated by A12 (d) because this is a third surface reading it:
    REFUSED naming the fixture and the offending stamp, never dropped."""
    late = _board(observed_by="2026-08-22 00:00:00")
    with pytest.raises(availarm.RowInadmissible, match="observed_by"):
        _rows(_even_view(), board=late)
    with pytest.raises(availarm.RowInadmissible, match="2627:alpha:bravo"):
        _rows(_even_view(), board=_board(cutoff="2026-08-30 00:00:00"))


def test_the_season_ledger_is_the_only_door_a_result_comes_through():
    """The results file is a REQUEST to score rows the ledger carries."""
    with pytest.raises(matchboard.MatchboardError, match="results ledger"):
        availarm.score(_board(), [_result()], snapshot=_even_view(),
                       ledger=_ledger())


def test_a_club_the_snapshot_does_not_carry_is_SquadEmpty_not_a_zero_feature():
    with pytest.raises(availarm.SquadEmpty, match="bravo"):
        _rows(_view({"alpha": _squad(11, team_key="alpha", minutes=270)}))


# ==========================================================================
# 3. abstention — A12 (b)
# ==========================================================================

def test_no_qualifying_snapshot_files_an_abstention_and_scores_nothing():
    """A12 (b): the capture began 2026-08-27, so "MW1 and MW2 are abstentions
    by construction" and this arm's scored record starts strictly after its
    input's archive does. An arm that scored weeks its input had never observed
    would be manufacturing a track record."""
    row = _rows(None)[0]
    assert tuple(row) == availarm.ABSTENTION_FIELDS
    assert row["abstained"] is True
    assert row["reason"] == availarm.ABSTENTION_REASON == "no_snapshot"
    assert row["arm"] == availarm.ARM
    assert row["fixture_id"] == "2627:alpha:bravo"
    assert row["run_digest"] == "3a" * 32
    assert availarm.is_abstention(row) is True


def test_an_abstention_row_carries_no_probability_feature_or_score_field():
    row = _rows(None)[0]
    for absent in ("probs_raw", "probs_avail", "feat_home", "feat_away",
                   "weight_basis_home", "weight_basis_away", "k_avail",
                   "snapshot_stamp", "snapshot_sha256", "outcome", "rps_raw",
                   "rps_avail", "rps_uniform", "matchweek", "ingest"):
        assert absent not in row


def test_abstentions_are_counted_and_never_scored(tmp_path):
    """"any aggregate over this ledger is an aggregate over scored rows and
    must print the abstention count beside itself, because an aggregate that
    hides its denominator is the oldest trick in forecasting"."""
    path = tmp_path / "avail.jsonl"
    availarm.append_shadow(path, _rows(None))
    availarm.append_shadow(path, availarm.score(
        _board_for("2627:charlie:delta"),
        [_result("2627:charlie:delta", hg=0, ag=1)],
        snapshot=_view({"charlie": _squad(11, team_key="charlie", minutes=270),
                        "delta": _squad(11, team_key="delta", minutes=270,
                                        first=101)}),
        ledger=_ledger(_played("2627:charlie:delta", 0, 1))))

    tally = availarm.tally(availarm.read_shadow(path))
    assert tally["n_rows"] == 2
    assert tally["n_scored"] == 1 and tally["n_abstained"] == 1
    assert tally["mean_rps_avail"] is not None


def test_the_arm_never_reads_a_snapshot_observed_after_the_issuance_clock(
        tmp_path, monkeypatch):
    """The two-clock discipline, end to end. The archive holds one snapshot,
    pulled AFTER the issuance's knowledge clock; the arm must abstain rather
    than borrow it."""
    raw, manifest = tmp_path / "raw", tmp_path / "manifest.jsonl"
    _archive(raw, manifest, "2026-08-27T02:30:39Z")

    early = availarm.snapshot_for("2026-08-21 00:00:00", raw_dir=raw,
                                  manifest_path=manifest)
    assert early is None, "nothing was observed by then, so there is no view"

    late = availarm.snapshot_for("2026-08-27T09:00:00Z", raw_dir=raw,
                                 manifest_path=manifest)
    assert late is not None and late.stamp == "20260827T023039Z"


def test_a_missing_or_edited_snapshot_is_the_arms_own_typed_refusal(tmp_path):
    """A12 item 5 puts `SnapshotMissing` and `SnapshotDigestMismatch` in the
    arm's family. The capture raises its own; the arm re-raises them under the
    names the entry pre-states, so an operator reading a STOP line sees the
    type the ledger names."""
    raw, manifest = tmp_path / "raw", tmp_path / "manifest.jsonl"
    _archive(raw, manifest, "2026-08-27T02:30:39Z")
    blob = next(raw.glob("*.json.gz"))

    kept = blob.read_bytes()
    blob.unlink()
    with pytest.raises(availarm.SnapshotMissing):
        availarm.snapshot_for("2026-08-27T09:00:00Z", raw_dir=raw,
                              manifest_path=manifest)
    assert issubclass(availarm.SnapshotMissing, availarm.AvailArmError)

    blob.write_bytes(gzip.compress(b'{"elements": [], "teams": []}', mtime=0))
    with pytest.raises(availarm.SnapshotDigestMismatch):
        availarm.snapshot_for("2026-08-27T09:00:00Z", raw_dir=raw,
                              manifest_path=manifest)
    blob.write_bytes(kept)


def test_an_unmapped_club_is_a_hard_error_on_the_whole_run(tmp_path):
    """A12 (c): "An unmapped team is a hard error on the arm's whole run for
    that snapshot, never a silent skip of one club's players" — a feature
    computed over nineteen clubs' worth of a twenty-club payload would be a
    wrong number wearing a right number's name. The capture's own
    `TeamUnmapped` is let through UNTRANSLATED, because it is the same fact.

    Built byte-first: `pull` maps every club as it writes and would have refused
    this payload on the way IN. What is under test is the way OUT — an archived
    snapshot whose spelling the registry no longer resolves, read by the arm.
    """
    from epl.tests import test_availability as cap

    raw, manifest = tmp_path / "raw", tmp_path / "manifest.jsonl"
    names = [(i, "Arsnal" if n == "Arsenal" else n) for i, n in cap.FPL_TEAMS]
    _hand_archive(raw, manifest, "2026-08-27T02:30:39Z", cap._payload(
        [cap._player(i, team=(i % 20) + 1, minutes=90) for i in range(1, 41)],
        teams=cap._team_rows(names)))

    with pytest.raises(av.TeamUnmapped, match="Arsnal"):
        availarm.snapshot_for("2026-08-27T09:00:00Z", raw_dir=raw,
                              manifest_path=manifest)


# ==========================================================================
# 4. the append-only file — A12 (d)
# ==========================================================================

def _filed(tmp_path, rows) -> Path:
    path = tmp_path / "avail.jsonl"
    availarm.append_shadow(path, rows)
    return path


def test_the_same_row_filed_twice_is_a_no_op(tmp_path):
    path = _filed(tmp_path, _rows(_even_view()))
    again = availarm.append_shadow(path, _rows(_even_view()))
    assert again == {"appended": 0, "repeated": 1}
    assert len(availarm.read_shadow(path)) == 1


def test_a_disagreeing_re_file_is_refused_naming_both_rows(tmp_path):
    path = _filed(tmp_path, _rows(_even_view()))
    other = _rows(_view({"alpha": _squad(11, team_key="alpha", minutes=270),
                         "bravo": _squad(11, team_key="bravo", minutes=270,
                                         first=101)}))
    with pytest.raises(availarm.RowConflict, match="2627:alpha:bravo"):
        availarm.append_shadow(path, other)
    assert len(availarm.read_shadow(path)) == 1


def test_nothing_is_written_unless_every_row_in_the_batch_passes(tmp_path):
    path = _filed(tmp_path, _rows(_even_view()))
    good = availarm.score(
        _board_for("2627:charlie:delta"),
        [_result("2627:charlie:delta", hg=0, ag=1)],
        snapshot=_view({"charlie": _squad(11, team_key="charlie", minutes=270),
                        "delta": _squad(11, team_key="delta", minutes=270,
                                        first=101)}),
        ledger=_ledger(_played("2627:charlie:delta", 0, 1)))
    bad = _rows(_view({"alpha": _squad(11, team_key="alpha", minutes=270),
                       "bravo": _squad(11, team_key="bravo", minutes=270,
                                       first=101)}))
    with pytest.raises(availarm.RowConflict):
        availarm.append_shadow(path, [*good, *bad])
    assert len(availarm.read_shadow(path)) == 1, (
        "a batch with one bad row appends none of them, so the re-run after "
        "the fix is a clean run rather than a partial repair")


# ==========================================================================
# 5. verification — A12 (f)
# ==========================================================================

def _archive(raw: Path, manifest: Path, when: str, *,
             squads=None, rename=None) -> dict:
    """A synthetic archive: one raw payload, one attesting manifest line.

    Written through the CAPTURE's own `pull`, so what `verify` reads back is
    what a real pull would have written and not a hand-built fixture.
    """
    from epl.tests import test_availability as cap

    names = list(cap.FPL_TEAMS)
    if rename is not None:
        names = [(i, rename[1] if n == rename[0] else n) for i, n in names]
    players = squads if squads is not None else [
        cap._player(i, team=(i % 20) + 1, minutes=90, now_cost=50)
        for i in range(1, 41)]
    payload = cap._payload(players, teams=cap._team_rows(names))
    return av.pull(fetcher=lambda url: cap._blob(payload), now=when,
                   raw_dir=raw, ledger_path=raw / "ledger.jsonl",
                   manifest_path=manifest)


def _hand_archive(raw: Path, manifest: Path, when: str, payload: dict) -> dict:
    """An archive written BYTE-FIRST, for a payload `pull` would never accept.

    The capture maps every club as it writes, so a spelling the registry does
    not know cannot be PULLED at all — and can perfectly well be sitting in an
    archive that was pulled before the registry changed under it. A12 (c) makes
    reading one a hard error on the arm's whole run, so the case has to be built
    here rather than through the capture that refuses it first.
    """
    from epl.tests import test_availability as cap

    blob = cap._blob(payload)
    stamp = av.stamp_for(when)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / av.raw_name(stamp)).write_bytes(gzip.compress(blob, mtime=0))
    line = {"observed_at": av.iso_z(when), "raw": av.raw_name(stamp),
            "season": av.SEASON, "sha256": av.sha256_bytes(blob),
            "stamp": stamp, "n_players": len(payload["elements"])}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")
    return line


def _real_squads() -> list[dict]:
    """Twenty clubs, eleven players each at 270 minutes, with Arsenal one down.

    Team 1 is Arsenal in the capture suite's spelling table, so this drives the
    minutes branch on a payload the capture will actually accept.
    """
    from epl.tests import test_availability as cap

    out = []
    for team in range(1, 21):
        for i in range(11):
            pid = team * 100 + i
            status = "i" if (team == 1 and i == 0) else "a"
            out.append(cap._player(pid, team=team, status=status, minutes=270,
                                   now_cost=50))
    return out


def _real_board(**overrides) -> dict:
    """A board over two real club keys, so a real snapshot can price it."""
    rows = matchboard.derive_rows(
        _spread_rows(), fixture_ids=("2627:arsenal:aston_villa",),
        facts={"2627:arsenal:aston_villa": {"home": "arsenal",
                                            "away": "aston_villa",
                                            "date": "2026-08-28"}})
    doc = _board(rows=rows, cutoff="2026-08-27 00:00:00",
                 observed_by="2026-08-27 00:00:00")
    doc.update(overrides)
    return doc


def _verifiable(tmp_path):
    """A filed ledger plus the archive it was derived from."""
    raw, manifest = tmp_path / "raw", tmp_path / "manifest.jsonl"
    _archive(raw, manifest, "2026-08-26T09:00:00Z", squads=_real_squads())
    view = availarm.snapshot_for("2026-08-27 00:00:00", raw_dir=raw,
                                 manifest_path=manifest)
    board = _real_board()
    rows = availarm.score(
        board, [_result("2627:arsenal:aston_villa", hg=2, ag=0)],
        snapshot=view,
        ledger=season_mod.resolve_ledger(
            [{"observed_at": "2026-08-29T09:00:00",
              "date_played": "2026-08-28",
              "fixture_id": "2627:arsenal:aston_villa", "hg": 2, "ag": 0}],
            identify=lambda row: str(row["fixture_id"])))
    path = tmp_path / "avail.jsonl"
    availarm.append_shadow(path, rows)
    return {"path": path, "raw": raw, "manifest": manifest, "rows": rows}


def _reverify(bits, **kw):
    return availarm.verify(bits["path"], raw_dir=bits["raw"],
                           manifest_path=bits["manifest"], **kw)


def _rewrite(path: Path, rows) -> None:
    from epl import leaguesim
    path.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows),
                    encoding="utf-8")


def test_verify_passes_a_ledger_that_re_derives(tmp_path):
    bits = _verifiable(tmp_path)
    report = _reverify(bits)
    assert report["n_rows"] == 1 and report["n_scored"] == 1
    assert report["n_abstained"] == 0
    assert report["arm"] == "dc_1x2_avail"
    assert report["rule_version"] == "dc-1x2-avail-1"
    assert report["k_avail"] == 1.0


def test_verify_re_derives_the_features_from_the_bytes(tmp_path):
    """A12 (f) step 3: the features are re-derived FROM THE SNAPSHOT'S BYTES,
    not recomputed from the row's own fields — which is the only version of
    this check that can catch a row whose feature was never what the archive
    said."""
    bits = _verifiable(tmp_path)
    rows = availarm.read_shadow(bits["path"])
    rows[0]["feat_home"] = rows[0]["feat_home"] + 1e-9
    _rewrite(bits["path"], rows)
    with pytest.raises(availarm.AvailMismatch, match="home"):
        _reverify(bits)


def test_verify_re_derives_every_cell_of_probs_avail(tmp_path):
    bits = _verifiable(tmp_path)
    rows = availarm.read_shadow(bits["path"])
    rows[0]["probs_avail"]["draw"] += 1e-9
    _rewrite(bits["path"], rows)
    with pytest.raises(availarm.AvailMismatch, match="draw"):
        _reverify(bits)


def test_verify_refuses_a_row_filed_under_another_rules_name(tmp_path):
    """One field at a time, each from the PRISTINE row.

    Mutating in place would leave the previous round's damage on the file, and
    then every later assertion would be satisfied by the first refusal instead
    of by the field it names — a loop that tests one thing four times.
    """
    bits = _verifiable(tmp_path)
    pristine = availarm.read_shadow(bits["path"])
    for field, value in (("rule_version", "dc-1x2-avail-2"),
                         ("schema_version", "epl-avail-shadow-2"),
                         ("arm", "dc_1x2_recal")):
        rows = [dict(row) for row in pristine]
        rows[0][field] = value
        _rewrite(bits["path"], rows)
        with pytest.raises(availarm.SchemaMismatch, match=field):
            _reverify(bits)

    # The constant gets its own round, and the row is made INTERNALLY
    # CONSISTENT at the other value on purpose: step 4 re-derives `probs_avail`
    # from the row's OWN `k_avail` and is satisfied by it, so step 5 is the only
    # thing between a row computed under a rule this repository does not hold
    # and the ledger. That ordering is what A12 (f) steps 4 and 5 are for, and a
    # row with a bare field swapped would never reach the second one.
    rows = [dict(row) for row in pristine]
    rows[0]["k_avail"] = 0.5
    rows[0]["probs_avail"] = availarm.adjust(
        rows[0]["probs_raw"], rows[0]["feat_home"], rows[0]["feat_away"],
        k_avail=0.5)
    rows[0]["rps_avail"] = matchboard.rps(rows[0]["probs_avail"],
                                          rows[0]["outcome"])
    _rewrite(bits["path"], rows)
    with pytest.raises(availarm.SchemaMismatch, match="k_avail"):
        _reverify(bits)

    _rewrite(bits["path"], pristine)
    assert _reverify(bits)["n_scored"] == 1, (
        "and the undamaged row still re-derives, so what the four rounds "
        "refused was the damage and not the fixture")


def test_verify_re_derives_which_snapshot_the_row_should_have_used(tmp_path):
    """A12 (f) step 2: "a row that used a snapshot the selection rule would not
    have chosen is SchemaMismatch". Here a SECOND, later snapshot enters the
    archive after the row was filed — and the row is still right, because the
    selection is re-derived at the ROW's own `observed_by` and not at today's
    clock."""
    bits = _verifiable(tmp_path)
    _archive(bits["raw"], bits["manifest"], "2026-08-28T09:00:00Z",
             squads=_real_squads())
    assert _reverify(bits)["n_scored"] == 1

    rows = availarm.read_shadow(bits["path"])
    rows[0]["snapshot_stamp"] = "20260828T090000Z"
    rows[0]["snapshot_sha256"] = availarm.snapshot_for(
        "2026-08-29T00:00:00Z", raw_dir=bits["raw"],
        manifest_path=bits["manifest"]).sha256
    _rewrite(bits["path"], rows)
    with pytest.raises(availarm.SchemaMismatch, match="selection"):
        _reverify(bits)


def test_verify_refuses_a_snapshot_the_archive_no_longer_holds(tmp_path):
    bits = _verifiable(tmp_path)
    next(bits["raw"].glob("*.json.gz")).unlink()
    with pytest.raises(availarm.SnapshotMissing):
        _reverify(bits)


def test_verify_recomputes_all_three_scores_and_the_sum(tmp_path):
    """Each score from the pristine row, for the reason the rule-name test
    gives: damage left on the file makes every later round pass on the first
    refusal rather than on the one it names."""
    bits = _verifiable(tmp_path)
    pristine = availarm.read_shadow(bits["path"])
    for field in ("rps_raw", "rps_avail", "rps_uniform"):
        rows = [dict(row) for row in pristine]
        rows[0][field] = 0.123456
        _rewrite(bits["path"], rows)
        with pytest.raises(availarm.AvailMismatch, match=field):
            _reverify(bits)


def test_verify_refuses_an_inadmissible_row_on_the_file(tmp_path):
    bits = _verifiable(tmp_path)
    rows = availarm.read_shadow(bits["path"])
    rows[0]["observed_by"] = "2026-08-29 00:00:00"
    _rewrite(bits["path"], rows)
    with pytest.raises(availarm.RowInadmissible):
        _reverify(bits)


def test_verify_refuses_two_rows_claiming_one_key(tmp_path):
    bits = _verifiable(tmp_path)
    rows = availarm.read_shadow(bits["path"])
    _rewrite(bits["path"], [*rows, *rows])
    with pytest.raises(availarm.RowConflict):
        _reverify(bits)


def test_verify_checks_an_abstention_row_for_the_absence_of_every_score_field(
        tmp_path):
    bits = _verifiable(tmp_path)
    abstention = _rows(None)[0]
    _rewrite(bits["path"], [*availarm.read_shadow(bits["path"]), abstention])
    assert _reverify(bits)["n_abstained"] == 1

    smuggled = {**abstention, "rps_avail": 0.1}
    _rewrite(bits["path"], [*availarm.read_shadow(bits["path"])[:1], smuggled])
    with pytest.raises(availarm.SchemaMismatch, match="rps_avail"):
        _reverify(bits)


def test_verify_refuses_an_empty_archive_rather_than_skipping(tmp_path):
    """CI has no `data/`: this command REFUSES there, loudly and correctly.
    A verification that quietly declines to verify is worse than one that was
    never run, because it prints something.

    The type is A12 (f) step 1's own: the manifest is the ATTESTATION, and a
    row citing a line the manifest does not carry cannot be re-derived at all,
    which is `SnapshotMissing` and not a schema question.
    """
    bits = _verifiable(tmp_path)
    bits["manifest"].write_text("", encoding="utf-8")
    with pytest.raises(availarm.SnapshotMissing, match="0 line"):
        _reverify(bits)


# ==========================================================================
# 6. the shadow layer reads no clock
# ==========================================================================

def test_the_arm_reads_no_clock_and_moving_the_clock_proves_it(tmp_path,
                                                               monkeypatch):
    """A row is a function of the bundle, the archive and the frozen rule."""
    import datetime as real_datetime
    import sys
    import time as real_time

    before = availarm.score(_board(), [_result()], snapshot=_even_view(),
                            ledger=_ledger(_played()))

    class _Frozen(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):                              # pragma: no cover
            raise AssertionError("the arm read a wall clock")
        utcnow = now

    monkeypatch.setattr(real_datetime, "datetime", _Frozen)
    monkeypatch.setattr(real_time, "time",
                        lambda: (_ for _ in ()).throw(
                            AssertionError("the arm read a wall clock")))
    monkeypatch.setitem(sys.modules, "datetime", real_datetime)
    monkeypatch.setitem(sys.modules, "time", real_time)

    after = availarm.score(_board(), [_result()], snapshot=_even_view(),
                           ledger=_ledger(_played()))
    assert before == after


# ==========================================================================
# 7. the command — A12 (e), (f)
# ==========================================================================

def test_the_command_is_the_one_A12_named_with_the_two_modes():
    assert availarm.MODES == ("verify", "score")
    assert availarm.SHADOW_PATH.name == "epl_avail_shadow.jsonl"
    assert availarm.SHADOW_PATH.parent.name == "reports"
    assert availarm.AUDIT_PATH.name == "epl_avail_audit.md"


def test_a_refusal_is_a_STOP_line_and_exit_2_not_a_traceback(tmp_path, capsys):
    """And a machine without the archive REFUSES rather than reporting a pass.

    A12 (f): "CI has no `data/`: the command refuses there, loudly". The r6
    command touched the archive only inside its row loop, so an empty ledger on
    a machine holding no snapshots exited 0 — the rule implemented backwards,
    and pinned that way by this test's own first assertion. Both objects A12 (f)
    needs are named: the manifest is the attestation, the raw directory is the
    bytes.
    """
    code = availarm.main(["verify", "--ledger", str(tmp_path / "nope.jsonl"),
                          "--raw-dir", str(tmp_path / "raw"),
                          "--manifest", str(tmp_path / "manifest.jsonl")])
    assert code == 2, "no manifest is no attestation, and that is a refusal"
    assert capsys.readouterr().err.startswith("STOP: SnapshotMissing:")

    (tmp_path / "manifest.jsonl").write_text("", encoding="utf-8")
    code = availarm.main(["verify", "--ledger", str(tmp_path / "nope.jsonl"),
                          "--raw-dir", str(tmp_path / "raw"),
                          "--manifest", str(tmp_path / "manifest.jsonl")])
    assert code == 2, "and no archive is no bytes, which is also a refusal"
    assert "STOP: SnapshotMissing:" in capsys.readouterr().err

    bits = _verifiable(tmp_path)
    next(bits["raw"].glob("*.json.gz")).unlink()
    code = availarm.main(["verify", "--ledger", str(bits["path"]),
                          "--raw-dir", str(bits["raw"]),
                          "--manifest", str(bits["manifest"])])
    assert code == 2
    assert capsys.readouterr().err.startswith("STOP: SnapshotMissing:")


def test_the_command_prints_the_provisional_sentence_the_audit_rule_binds(
        tmp_path, capsys):
    """A12 (g): until the tenth scored matchweek's audit entry exists, EVERY
    summary of this arm's record carries the sentence "the input feed is under
    audit; this record is provisional". A language rule in the A8 (e) sense,
    binding on every surface this project writes — including this one."""
    bits = _verifiable(tmp_path)
    assert availarm.main(["verify", "--ledger", str(bits["path"]),
                          "--raw-dir", str(bits["raw"]),
                          "--manifest", str(bits["manifest"])]) == 0
    out = capsys.readouterr().out
    assert availarm.PROVISIONAL_SENTENCE in out
    assert "the input feed is under audit; this record is provisional" == \
        availarm.PROVISIONAL_SENTENCE


# ==========================================================================
# 8. the entry and the code say the same numbers
# ==========================================================================

def _prestated() -> dict[str, str]:
    """A12 item 1's constants block, parsed out of the amendment itself.

    The point of parsing rather than restating: a later edit to either side is
    caught. This is the same discipline `test_recal.py` applies to A8's
    grounding report, one level up — the ledger IS the specification.
    """
    text = AMENDMENTS.read_text(encoding="utf-8")
    entry = text[text.index("## A12 —"):]
    block = entry[entry.index("**1. The rule's constants, all of them.**"):]
    block = block[block.index("```") + 3:]
    block = block[:block.index("```")]
    out: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        # The arrow rows carry an `=` INSIDE their value (`-> u_p = 0.5`), so
        # the arrow has to be tried first or the split lands mid-value and
        # every arrow key comes back malformed.
        key, _, value = line.partition("→" if "→" in line else "=")
        out[key.strip()] = value.strip()
    return out


def test_the_constants_block_is_the_amendments_own_numbers():
    """Every constant of A12's rule, read out of the entry and compared to the
    code. `k_avail` is a PRIOR: if this test ever fails, either the code drifted
    from a ruling or somebody changed a ruling without a new amendment, and
    both are exactly what this file exists to stop."""
    pre = _prestated()
    assert float(pre["k_avail"].split()[0]) == availarm.K_AVAIL == 1.0
    assert "a prior, not a fit" in pre["k_avail"]
    assert pre["null d-chance"].startswith("u_p = 0.5")
    assert availarm.NULL_CHANCE_UNAVAIL == 0.5
    assert pre["i, s"].startswith("u_p = 1.0")
    assert availarm.FLAT_UNAVAIL_STATUSES == ("i", "s")
    assert "excluded" in pre["u, n"]
    assert availarm.EXCLUDED_STATUSES == ("u", "n")
    assert int(pre["minutes switchover"].split()[0]) \
        == availarm.MINUTES_SWITCHOVER == 2970
    assert "3 × 990" in pre["minutes switchover"]
    assert pre["weight fallback"].startswith("now_cost share")
    assert availarm.WEIGHT_BASIS_FALLBACK == "now_cost"
    assert pre["rule_version"] == availarm.RULE_VERSION
    assert pre["schema_version"] == availarm.SCHEMA_VERSION
    assert pre["ledger"] == f"reports/{availarm.SHADOW_FILENAME}"
    assert pre["audit file"] == f"reports/{availarm.AUDIT_FILENAME}"


def test_the_row_schema_is_the_table_A12_prints():
    """A12 (d)'s table, read out of the entry's own markdown, against
    `ROW_FIELDS`. A field this ledger was not authorised to carry is as much a
    schema change as a missing one."""
    text = AMENDMENTS.read_text(encoding="utf-8")
    entry = text[text.index("## A12 —"):]
    table = entry[entry.index("| field | what it is |"):]
    table = table[:table.index("An **abstention row**")]
    named: list[str] = []
    for line in table.splitlines():
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1]
        named += [f.strip().strip("`") for f in cell.split(",")]
    # `schema_version` is ruled onto every row by the paragraph above the table
    assert set(named) | {"schema_version"} == set(availarm.ROW_FIELDS)


def test_the_expected_effect_is_an_expectation_and_fires_nothing():
    """A12 item 6 pre-states 0 to +0.0002 mean RPS and says in terms that
    nothing fires if the ledger lands outside it. So there is no threshold, no
    verdict and no pass rule anywhere in this arm."""
    text = Path(availarm.__file__).read_text(encoding="utf-8")
    for banned in ("PASS", "FAIL", "verdict", "threshold", "adopt"):
        assert banned not in text, (
            f"{banned!r} in an arm A12 gives no pass rule: this ledger reports")


@pytest.mark.skipif(not AVAIL_LEDGER.exists(),
                    reason="no matchweek has filed into the shadow ledger yet")
def test_the_committed_shadow_ledger_is_this_schema_and_nothing_else():
    for row in availarm.read_shadow(AVAIL_LEDGER):
        assert row["schema_version"] == availarm.SCHEMA_VERSION
        assert row["arm"] == availarm.ARM
        assert row["rule_version"] == availarm.RULE_VERSION
        fields = (availarm.ABSTENTION_FIELDS if availarm.is_abstention(row)
                  else availarm.ROW_FIELDS)
        assert tuple(row) == fields


# ==========================================================================
# 9. the live cycle's step 9, and the boundary A12 (e) moved
# ==========================================================================

def test_the_cycle_gains_step_nine_and_calls_it_through_the_arms_own_main():
    from epl import livecycle

    assert livecycle.DEFAULT_STEPS["avail"] is livecycle._step_avail
    assert list(livecycle.DEFAULT_STEPS) == ["forecast", "check", "matchboard",
                                             "shadow", "avail"]


def test_availarm_is_the_only_bridge_between_the_capture_and_the_cycle():
    """A12 (e), as executable rule. The capture module imports no model module
    (unchanged); `epl/livecycle.py` does not import `epl.availability` DIRECTLY;
    and `epl.availarm` imports both sides, because it is the authorised bridge.

    Asserted over the import graph rather than over a substring: the live cycle
    now legitimately mentions availability in its prose, and a string test would
    have to be softened again the first time it did.
    """
    import ast

    def imports_of(module) -> set[str]:
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                names |= {f"{base}.{alias.name}" for alias in node.names}
        return names

    from epl import livecycle

    cycle = imports_of(livecycle)
    assert "epl.availability" not in cycle
    assert "epl.availarm" in cycle

    arm = imports_of(availarm)
    assert "epl.availability" in arm and "epl.matchboard" in arm

    capture = imports_of(av)
    assert not any(name.startswith("epl.availarm") for name in capture)
    for forbidden in ("epl.leaguesim", "epl.particles", "epl.elo", "epl.fit"):
        assert forbidden not in capture


def test_a_dry_run_scores_nothing_and_writes_no_avail_row(tmp_path):
    """The cycle's dry run has not ingested, so it must not score — and that
    holds for step 9 exactly as it holds for steps 7 and 8."""
    from epl.tests import test_livecycle as lc

    ledger = tmp_path / "avail.jsonl"
    out = lc._cycle(tmp_path, dry_run=True, avail_ledger=ledger)
    assert out["avail"] is None
    assert out["_steps"].named("avail") == []
    assert not ledger.exists()


def test_the_cycle_scores_the_avail_arm_from_the_same_bundle_and_rows(tmp_path):
    from epl.tests import test_livecycle as lc

    out = lc._cycle(tmp_path)
    board_call = out["_steps"].named("matchboard")[0]
    avail_call = out["_steps"].named("avail")[0]
    assert avail_call["directory"] == board_call["directory"]
    assert avail_call["rows"] == board_call["rows"]
    assert out["avail"]["appended"] == len(lc.MW1_SCORES)
    assert "avail_shadow" in out["digests"]


def test_the_step_turns_a_refusal_into_this_cycles_refusal(tmp_path):
    """Mirrors step 8: a non-zero exit from the arm's own `main` is the cycle's
    refusal, and the arm has already printed its STOP line above it."""
    from epl import livecycle

    with pytest.raises(livecycle.ScorecardMismatch, match="epl.availarm"):
        livecycle._step_avail(directory=tmp_path / "nowhere",
                              results_file=tmp_path / "none.jsonl",
                              ledger=tmp_path / "avail.jsonl",
                              season_root=None, verbose=False)
    assert not (tmp_path / "avail.jsonl").exists()


# ==========================================================================
# 10. the side door, shut — the PIT guard is on the WRITE path (r7 B1)
# ==========================================================================
#: A12 (b) selects a snapshot by OUR clock: "keep the lines whose `observed_at`
#: is at or before the issuance's `observed_by`". Until r7 that rule lived only
#: in the canonical selector, and `score`/`append_shadow` took whatever
#: `AsOfSnapshot` a caller handed them — so a board observed 2026-08-21 could be
#: priced with a snapshot pulled on 2026-08-27 and the row filed without a
#: murmur. These tests hold the guard where the row is MADE and where it is
#: WRITTEN, because those are the two places a fabricated information set
#: actually becomes a record.

def _future_view() -> av.AsOfSnapshot:
    """The `_even_view()` squads, observed six days AFTER the board's clock."""
    home = _squad(11, team_key="alpha", minutes=270)
    away = _squad(11, team_key="bravo", minutes=270, first=101)
    home[0] = {**home[0], "status": "i"}
    return _view({"alpha": home, "bravo": away},
                 stamp="20260827T023039Z",
                 observed_at="2026-08-27T02:30:39Z")


def test_scoring_refuses_a_snapshot_observed_after_the_issuance_clock():
    """The side door A12 (b) never authorised, shut at the scoring path.

    `snapshot_for` picks correctly; `score` used to accept ANY view a caller
    handed it. The two-clock discipline is a property of the rule, not of the
    one function that happens to implement the selection.
    """
    with pytest.raises(availarm.SchemaMismatch, match="observed"):
        _rows(_future_view())
    with pytest.raises(availarm.SchemaMismatch, match="2026-08-27"):
        availarm.forecast_rows(_board(), snapshot=_future_view())


def test_the_write_path_refuses_a_row_whose_snapshot_postdates_its_clock(
        tmp_path):
    """And the guard is on the FILE, not only on the function above it.

    A row's `snapshot_stamp` IS its snapshot's `observed_at` floored to the
    second, so the ledger can answer "was this observed in time?" from the row
    alone — without the manifest, which is exactly the object a caller could
    substitute.
    """
    row = dict(_one())
    row["snapshot_stamp"] = "20260827T023039Z"
    path = tmp_path / "avail.jsonl"
    with pytest.raises(availarm.SchemaMismatch, match="observed"):
        availarm.append_shadow(path, [row])
    assert not path.exists(), "nothing is written when a row is refused"


def test_a_snapshot_observed_at_the_clock_itself_is_admissible():
    """"at or before" — the bound is INCLUSIVE, and a boundary this arm got
    wrong by a second would silently abstain on every same-instant pull."""
    view = _view({"alpha": _squad(11, team_key="alpha", minutes=270),
                  "bravo": _squad(11, team_key="bravo", minutes=270,
                                  first=101)},
                 stamp="20260821T000000Z", observed_at="2026-08-21T00:00:00Z")
    row = _rows(view)[0]
    assert row["snapshot_stamp"] == "20260821T000000Z"


# ==========================================================================
# 11. the trust anchor — a manifest is present or the arm STOPs (r7 B3)
# ==========================================================================
#: A12 (b) names ONE manifest: `epl/season/2026_27/availability_manifest.jsonl`,
#: tracked, and "the bytes are the record and the manifest is the attestation".
#: A missing file is not an archive that knows nothing — it is an archive
#: nobody can ask. Reading it as "no snapshot qualified" turned a typo into a
#: filed abstention, and A12 (d)'s `(fixture_id, run_digest)` idempotence then
#: made that fabricated row BLOCK the correct scored one for ever.

def test_a_missing_manifest_is_a_typed_stop_and_never_an_abstention(tmp_path):
    with pytest.raises(availarm.SnapshotMissing, match="manifest"):
        availarm.snapshot_for("2026-08-27T09:00:00Z",
                              raw_dir=tmp_path / "raw",
                              manifest_path=tmp_path / "nowhere.jsonl")


def test_a_present_but_empty_manifest_is_still_an_honest_abstention(tmp_path):
    """The distinction the fix turns on. A manifest that EXISTS and attests
    nothing is the archive before its first pull, and A12 (b) rules an
    abstention for it. A manifest that is not there attests nothing about
    anything, including about whether it is the tracked one."""
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("", encoding="utf-8")
    assert availarm.snapshot_for("2026-08-27T09:00:00Z",
                                 raw_dir=tmp_path / "raw",
                                 manifest_path=manifest) is None


def test_a_substituted_manifest_may_not_write_into_the_official_ledger(
        tmp_path):
    """A12 (b)'s trust anchor is the TRACKED manifest. The scoring entrypoint
    still takes `--manifest`/`--raw-dir` — they are what makes the suite
    CI-safe — but an untracked archive may not file into
    `reports/epl_avail_shadow.jsonl`, because a row there is a claim about the
    archive this repository tracks."""
    with pytest.raises(availarm.AvailArmError, match="official"):
        availarm.score_bundle(tmp_path / "bundle", tmp_path / "results.jsonl",
                              manifest_path=tmp_path / "manifest.jsonl")
    with pytest.raises(availarm.AvailArmError, match="official"):
        availarm.score_bundle(tmp_path / "bundle", tmp_path / "results.jsonl",
                              raw_dir=tmp_path / "raw",
                              ledger_path=availarm.SHADOW_PATH)


def test_the_official_ledger_is_the_default_and_an_override_is_a_choice(
        tmp_path):
    """And the guard is on the LEDGER, not on the flag: an override that writes
    somewhere else is exactly what the live cycle and this suite do."""
    with pytest.raises(availarm.AvailArmError, match="neither an issuance"):
        availarm.score_bundle(tmp_path / "bundle", tmp_path / "results.jsonl",
                              manifest_path=tmp_path / "manifest.jsonl",
                              ledger_path=tmp_path / "avail.jsonl")


# ==========================================================================
# 12. verification proves the row, it does not merely read it (r7 I1, I2)
# ==========================================================================

def test_verify_refuses_an_abstention_a_qualifying_snapshot_contradicts(
        tmp_path):
    """A12 (b) rules an abstention for one fact only — "if no manifest line
    qualifies". The r6 verifier checked an abstention's SHAPE and moved on, so
    a hand-written `no_snapshot` row for a fixture the archive could perfectly
    well have priced passed; and A12 (d)'s idempotence then made that row
    refuse the correct scored one for ever. The claim is re-derived from the
    tracked manifest, which is the one object this check needs."""
    bits = _verifiable(tmp_path)                # archive observed 2026-08-26
    board = _real_board()                       # observed_by 2026-08-27
    fabricated = availarm.abstention_row(board, board["rows"][0])
    _rewrite(bits["path"], [fabricated])
    with pytest.raises(availarm.SchemaMismatch, match="abstention"):
        _reverify(bits)


def test_verify_accepts_an_abstention_the_selection_rule_earns(tmp_path):
    """The other half, so the check above is not simply refusing everything."""
    bits = _verifiable(tmp_path)
    earned = _rows(None)[0]                     # observed_by 2026-08-21
    _rewrite(bits["path"], [*availarm.read_shadow(bits["path"]), earned])
    assert _reverify(bits)["n_abstained"] == 1


def test_verify_refuses_an_abstention_marker_that_is_not_the_literal_true(
        tmp_path):
    """`abstained: 1` reads as an abstention to one reader and as a scored row
    to the next — and a row that is a scored row to a reader who then finds no
    `probs_raw` on it is a traceback, not a refusal."""
    bits = _verifiable(tmp_path)
    smuggled = {**_rows(None)[0], "abstained": 1}
    _rewrite(bits["path"], [smuggled])
    with pytest.raises(availarm.SchemaMismatch, match="abstained"):
        _reverify(bits)
    assert availarm.is_abstention({"abstained": 1}) is False
    assert availarm.is_abstention({"abstained": True}) is True


def test_verify_refuses_a_scored_row_carrying_a_field_A12_never_named(
        tmp_path):
    """A12 (d)'s table is exact in both directions. The r6 verifier read the
    fields it wanted and never asked what else was on the row, so a ledger
    could grow a column nobody ruled."""
    bits = _verifiable(tmp_path)
    pristine = availarm.read_shadow(bits["path"])
    rows = [{**pristine[0], "market_price": 1.85}]
    _rewrite(bits["path"], rows)
    with pytest.raises(availarm.SchemaMismatch, match="market_price"):
        _reverify(bits)

    rows = [{k: v for k, v in pristine[0].items() if k != "ingest"}]
    _rewrite(bits["path"], rows)
    with pytest.raises(availarm.SchemaMismatch, match="ingest"):
        _reverify(bits)


def test_the_frozen_coefficient_is_not_a_parameter_of_any_filing_path():
    """A12: "`k_avail` is a PRIOR, not a fit"; it "changes only by a new
    amendment". The r6 module took it as a keyword on `score`, `score_bundle`
    AND `verify` — so 0.5 could be written and then blessed by
    `verify(..., k_avail=0.5)`, which is a repository holding a rule nobody
    ruled and a verifier agreeing with it.

    `adjust` and `tilt` keep theirs: they are the arithmetic A12 item 3's
    control is written against, and neither files anything.
    """
    import inspect

    for fn in (availarm.score, availarm.score_bundle, availarm.verify,
               availarm.forecast_rows, availarm.check_row):
        assert "k_avail" not in inspect.signature(fn).parameters, (
            f"{fn.__name__} takes the frozen prior as an argument")
    assert "k_avail" in inspect.signature(availarm.adjust).parameters


def test_the_write_path_refuses_a_row_under_another_constant(tmp_path):
    row = {**_one(), "k_avail": 0.5}
    with pytest.raises(availarm.SchemaMismatch, match="k_avail"):
        availarm.append_shadow(tmp_path / "avail.jsonl", [row])


# ==========================================================================
# 13. the source's domain — a clamp would reverse the ruled sign (r7 I4)
# ==========================================================================
#: A12 (b) writes `u_p = (100 - chance)/100` and then states, in terms, that
#: `feat_side` is "a number in `[0, 1]`". Nothing checked the source's domain,
#: so a `chance_of_playing_next_round` of 200 produced `u_p = -1` and a
#: NEGATIVE feature — a tilt with the wrong sign, moving a side's probability
#: the way it moves when players are AVAILABLE. Clamping would be worse than
#: refusing: it would silently price a payload the rule cannot read.

def test_a_chance_outside_the_sources_own_ladder_is_refused_not_clamped():
    with pytest.raises(av.AvailabilitySchemaDrift, match="200"):
        availarm.unavailability(_p(1, status="d", chance=200))
    with pytest.raises(av.AvailabilitySchemaDrift, match="-25"):
        availarm.unavailability(_p(1, status="d", chance=-25))
    # and the ladder's own ends stay admissible
    assert availarm.unavailability(_p(1, status="d", chance=0)) == 1.0
    assert availarm.unavailability(_p(1, status="d", chance=100)) == 0.0


def test_a_negative_weight_is_refused_rather_than_summed():
    with pytest.raises(av.AvailabilitySchemaDrift, match="minutes"):
        availarm.side_feature([_p(1, minutes=-90, now_cost=50),
                               _p(2, minutes=3000, now_cost=50)])
    with pytest.raises(av.AvailabilitySchemaDrift, match="now_cost"):
        availarm.side_feature([_p(1, minutes=0, now_cost=-50),
                               _p(2, minutes=0, now_cost=50)])


def test_the_feature_is_provably_in_the_unit_interval_A12_names():
    """The post-condition, asserted on the number rather than hoped for."""
    for squad in ([_p(i, status="i") for i in range(1, 12)],
                  _squad(11, team_key="alpha"),
                  [_p(1, status="d", chance=25), *_squad(10, team_key="alpha",
                                                         first=2)]):
        feat = availarm.side_feature(squad).feat
        assert 0.0 <= feat <= 1.0


def test_the_as_of_read_refuses_a_payload_outside_the_sources_domain(tmp_path):
    """And the refusal is at the ARCHIVE's door too, where the bytes are read:
    the arm's own check protects a hand-built view, this one protects every
    caller of the read side."""
    from epl.tests import test_availability as cap

    raw, manifest = tmp_path / "raw", tmp_path / "manifest.jsonl"
    players = [cap._player(i, team=(i % 20) + 1, minutes=90) for i in range(1, 41)]
    players[0] = {**players[0], "status": "d",
                  "chance_of_playing_next_round": 200}
    _hand_archive(raw, manifest, "2026-08-27T02:30:39Z",
                  cap._payload(players, teams=cap._team_rows(cap.FPL_TEAMS)))
    with pytest.raises(av.AvailabilitySchemaDrift, match="200"):
        availarm.snapshot_for("2026-08-27T09:00:00Z", raw_dir=raw,
                              manifest_path=manifest)

    players[0] = {**players[0], "chance_of_playing_next_round": None,
                  "minutes": -1}
    _hand_archive(raw, manifest, "2026-08-27T03:00:00Z",
                  cap._payload(players, teams=cap._team_rows(cap.FPL_TEAMS)))
    with pytest.raises(av.AvailabilitySchemaDrift, match="minutes"):
        availarm.snapshot_for("2026-08-27T09:00:00Z", raw_dir=raw,
                              manifest_path=manifest)


# ==========================================================================
# 14. the flight log can tell a scored week from a sat-out one (r7 I5)
# ==========================================================================

def _fake_main(rows):
    """A stand-in for `availarm.main` that files `rows` and exits 0."""
    def main(argv):
        ledger = argv[argv.index("--ledger") + 1]
        availarm.append_shadow(Path(ledger), rows)
        return 0
    return main


def test_step_nine_records_scored_and_abstained_and_a_real_repeated_count(
        tmp_path, monkeypatch):
    """A12 (e) puts step 9's tally in the journal and A12 (d) rules that "any
    aggregate over this ledger is an aggregate over scored rows and must print
    the abstention count beside itself". The r6 step returned `appended` and a
    hardcoded `repeated: 0`, so an all-abstention batch and an all-scored batch
    of the same size wrote the same journal line — which is the denominator
    A12 (d) exists to stop anyone hiding."""
    from epl import livecycle

    ledger = tmp_path / "avail.jsonl"
    results = tmp_path / "results.jsonl"
    results.write_text("".join(
        json.dumps(_result(fid, hg=2, ag=0)) + "\n"
        for fid in ("2627:alpha:bravo", "2627:charlie:delta")), encoding="utf-8")

    scored = _rows(_even_view())
    sat_out = availarm.score(
        _board_for("2627:charlie:delta"),
        [_result("2627:charlie:delta", hg=0, ag=1)], snapshot=None,
        ledger=_ledger(_played("2627:charlie:delta", 0, 1)))
    monkeypatch.setattr(availarm, "main", _fake_main([*scored, *sat_out]))

    got = livecycle._step_avail(directory=tmp_path, results_file=results,
                                ledger=ledger, season_root=None, verbose=False)
    assert got["appended"] == 2
    assert got["scored"] == 1 and got["abstained"] == 1
    assert got["repeated"] == 0

    # the same batch again: nothing new lands, and the count says so
    again = livecycle._step_avail(directory=tmp_path, results_file=results,
                                  ledger=ledger, season_root=None,
                                  verbose=False)
    assert again == {**got, "appended": 0, "scored": 0, "abstained": 0,
                     "repeated": 2}


def test_the_one_screen_prints_the_abstention_count_beside_the_denominator():
    """A12 (d)'s language rule, on the surface a human actually reads."""
    from epl import livecycle

    entry = {"outcome": "ran", "at": "2026-08-28T09:00:00Z",
             "season": "2026/27", "cutoff": "2026-08-28",
             "dry_run": False, "sources": {}, "ingested": {"fixtures": []},
             "issuance": None, "already_resolved": None, "check": None,
             "scorecard": {"appended": 2, "repeated": 0, "bundles": ["b"]},
             "shadow": {"appended": 2, "repeated": 0, "bundles": ["b"]},
             "avail": {"appended": 2, "repeated": 0, "bundles": ["b"],
                       "scored": 0, "abstained": 2},
             "digests": {}}
    screen = livecycle.render_summary(entry)
    assert "2 abstention(s)" in screen
    assert "0 scored" in screen
