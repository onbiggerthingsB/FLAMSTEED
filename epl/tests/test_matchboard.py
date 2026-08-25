"""A7 — the per-fixture matchboard, held to the amendment that pre-stated it.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_matchboard.py -q

Every number on this surface is derived from ONE thing: the retained scorelines
of the run that issued it. So the tests here are mostly about what the
derivation must refuse — a column read by its position instead of by its
ordinal, a standard error computed as if 20,000 correlated seasons were 20,000
independent draws, a scorecard row whose forecast did not precede the kickoff it
is scored against. Each of those produces a plausible number, which is why each
is paired with the input that tells the two apart.

CI HAS NO ``data/``. Everything below builds its own arrays; the one test that
reads the preserved opener bundle is guarded on its existence and skips.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import leaguesim, matchboard, season as season_mod

#: The preserved MW0 bundle. Present on the machine that issued it and nowhere
#: else, so every test that reads it is guarded.
COMMITTED_OPENER = Path("data/epl/sim/issuances/2026_27/2026-08-21")

#: A five-fixture synthetic season. Deliberately NOT in the order a reader would
#: guess: `fixture_ordinal` is a RANK among the SORTED ids, so a derivation that
#: uses the npz column position instead resolves the wrong club pair and the
#: wrong date, and does it silently.
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


def _arrays(scorelines, particle, ordinals) -> dict:
    """The three npz arrays a matchboard reads, shaped as the engine writes them."""
    return {"scorelines": np.asarray(scorelines, np.int8),
            "particle": np.asarray(particle, np.int16),
            "fixture_ordinals": np.asarray(ordinals, np.int32)}


def _spread_rows():
    """Four particles that disagree violently — the clustering's whole point.

    Particle 0 wins every season at home, 1 draws every season, 2 loses every
    season, 3 splits. Within a particle there is almost no variation and between
    particles there is nothing but; a binomial standard error over the 1,000
    seasons sees only the former and reports a number an order of magnitude too
    small.
    """
    per = 250
    particle = np.repeat(np.arange(4, dtype=np.int16), per)
    scorelines = np.zeros((4 * per, 1, 2), np.int8)
    scorelines[0 * per:1 * per] = (4, 0)                     # particle 0: home
    scorelines[1 * per:2 * per] = (1, 1)                     # particle 1: draw
    scorelines[2 * per:3 * per] = (0, 1)                     # particle 2: away
    scorelines[3 * per:3 * per + per // 2] = (2, 0)          # particle 3: split
    scorelines[3 * per + per // 2:4 * per] = (0, 2)
    return _arrays(scorelines, particle, [0])


# ==========================================================================
# 1. the column contract — an ordinal is a RANK, not a position
# ==========================================================================

def test_the_ordinal_is_resolved_as_a_rank_among_the_sorted_fixture_ids():
    """`epl/leaguesim.py:37` made readable, and pinned by a permuted season.

    The npz stores one column per UNPLAYED fixture and an ordinal per column.
    The ordinal is the rank of that fixture's id among all of the season's
    sorted ids — so with three unplayed fixtures out of five, the columns carry
    ordinals 0, 2 and 4 and not 0, 1 and 2. Reading the column position would
    name `charlie:delta` where the run priced `echo:foxtrot`.
    """
    scorelines = np.zeros((4, 3, 2), np.int8)
    scorelines[:, 0] = (1, 0)
    scorelines[:, 1] = (0, 0)
    scorelines[:, 2] = (0, 3)
    arrays = _arrays(scorelines, [0, 0, 1, 1], [4, 0, 2])

    rows = matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS)

    # ordinal order, whatever order the columns happen to be in
    assert [r["fixture_ordinal"] for r in rows] == [0, 2, 4]
    assert [r["fixture_id"] for r in rows] == [
        "2627:alpha:bravo", "2627:echo:foxtrot", "2627:india:juliet"]
    assert [(r["home"], r["away"]) for r in rows] == [
        ("alpha", "bravo"), ("echo", "foxtrot"), ("india", "juliet")]
    assert [r["date"] for r in rows] == ["2026-08-21", "2026-08-23", "2026-08-25"]

    # ...and the numbers travelled with the ordinal, not with the position:
    # column 1 (ordinal 0) was the 0-0, column 2 (ordinal 2) the 0-3.
    by_id = {r["fixture_id"]: r for r in rows}
    assert by_id["2627:alpha:bravo"]["probs"]["draw"] == 1.0
    assert by_id["2627:echo:foxtrot"]["probs"]["away"] == 1.0
    assert by_id["2627:india:juliet"]["probs"]["home"] == 1.0


def test_an_ordinal_the_season_cannot_resolve_is_refused():
    """A rows file whose ordinals do not index this season's ids is not this
    season's rows, and naming a fixture out of it would be a guess."""
    arrays = _arrays(np.zeros((4, 1, 2), np.int8), [0, 0, 1, 1], [99])
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS)
    assert "99" in str(exc.value)


def test_a_fixture_id_with_no_facts_is_refused_rather_than_left_blank():
    holed = {k: v for k, v in FACTS.items() if k != "2627:alpha:bravo"}
    arrays = _arrays(np.zeros((4, 1, 2), np.int8), [0, 0, 1, 1], [0])
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=holed)
    assert "2627:alpha:bravo" in str(exc.value)


# ==========================================================================
# 2. the invariants A7 pre-states, on every row
# ==========================================================================

def test_every_row_sums_to_one_and_the_margin_chain_is_monotone():
    """A7 *What is pre-stated* 2. The margin events are NESTED on one sample, so
    the chain is monotone BY CONSTRUCTION — a violation is a defect in the
    derivation and never a sampling accident."""
    rng = np.random.default_rng(11)
    n, f = 800, 6
    scorelines = rng.integers(0, 5, size=(n, f, 2)).astype(np.int8)
    particle = np.repeat(np.arange(40, dtype=np.int16), n // 40)
    arrays = _arrays(scorelines, particle, list(range(f)))
    ids = tuple(f"2627:t{i:02d}:u{i:02d}" for i in range(f))
    facts = {fid: {"home": f"t{i:02d}", "away": f"u{i:02d}",
                   "date": "2026-09-01"} for i, fid in enumerate(ids)}

    rows = matchboard.derive_rows(arrays, fixture_ids=ids, facts=facts)
    assert len(rows) == f
    for row in rows:
        p = row["probs"]
        assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-9
        assert row["p_marg_ge2"] >= row["p_marg_ge3"] >= row["p_marg_ge4"], (
            "the margin chain is monotone by construction; this is a derivation "
            "defect, not a sampling accident")
        assert row["e_margin"] >= 0.0
        assert row["n_sims"] == n
        assert row["n_particles"] == 40


def test_the_margin_is_unsigned_and_a_draw_contributes_zero():
    """A7's World-Cup semantics, pinned on a sample built to tell the two
    readings apart: a SIGNED margin would average these three seasons to zero
    and report `p_marg_ge2` on one side only."""
    scorelines = np.array([[[3, 0]], [[0, 3]], [[1, 1]], [[2, 0]]], np.int8)
    arrays = _arrays(scorelines, [0, 0, 1, 1], [0])
    row = matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS,
                                 facts=FACTS)[0]
    # |3| + |-3| + |0| + |2| = 8 over 4 seasons
    assert row["e_margin"] == pytest.approx(2.0, abs=1e-12)
    assert row["p_marg_ge2"] == pytest.approx(0.75, abs=1e-12)
    assert row["p_marg_ge3"] == pytest.approx(0.50, abs=1e-12)
    assert row["p_marg_ge4"] == pytest.approx(0.00, abs=1e-12)
    assert row["probs"] == {"home": 0.5, "draw": 0.25, "away": 0.25}


# ==========================================================================
# 3. the standard error clusters by particle — and the binomial is rejected
# ==========================================================================

def test_the_standard_errors_cluster_by_particle_not_over_the_sims():
    """A7 (a): a binomial SE over `n_sims` is a FAIL of the derivation, not a
    rounding difference.

    Built so the two answers cannot be confused: four particles that disagree
    almost completely, 250 seasons each. The cluster form sees the disagreement
    between the posterior draws; the binomial sees 1,000 independent coins that
    do not exist.
    """
    arrays = _spread_rows()
    row = matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS)[0]

    particle = arrays["particle"]
    hg = arrays["scorelines"][:, 0, 0].astype(float)
    ag = arrays["scorelines"][:, 0, 1].astype(float)
    home = (hg > ag).astype(float)

    expected = leaguesim.cluster_se(home, particle)
    binomial = float(np.sqrt(home.mean() * (1 - home.mean()) / home.size))

    assert row["probs_se"]["home"] == pytest.approx(expected, abs=1e-12)
    assert row["probs_se"]["home"] != pytest.approx(binomial, abs=1e-6)
    assert row["probs_se"]["home"] > 10 * binomial, (
        "the two forms must be materially different on this sample, or the "
        "test cannot tell which one the derivation used")

    # every SE on the row is the same form, including the margin ones
    margin = np.abs(hg - ag)
    assert row["e_margin_se"] == pytest.approx(
        leaguesim.cluster_se(margin, particle), abs=1e-12)
    for k in (2, 3, 4):
        assert row[f"p_marg_ge{k}_se"] == pytest.approx(
            leaguesim.cluster_se((margin >= k).astype(float), particle),
            abs=1e-12), k
        assert row[f"p_marg_ge{k}_se"] != pytest.approx(
            float(np.sqrt(row[f"p_marg_ge{k}"] * (1 - row[f"p_marg_ge{k}"])
                          / margin.size)), abs=1e-6), k


def test_a_row_carries_every_field_A7_names_and_nothing_else():
    """The field table of A7 (a), enumerated. A surface with an extra column is
    a surface nobody ruled on — (f) makes that a new amendment, not a detail."""
    arrays = _spread_rows()
    row = matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS)[0]
    assert set(row) == {
        "fixture_id", "fixture_ordinal", "date", "home", "away",
        "probs", "probs_se", "e_margin", "e_margin_se",
        "p_marg_ge2", "p_marg_ge3", "p_marg_ge4",
        "p_marg_ge2_se", "p_marg_ge3_se", "p_marg_ge4_se",
        "n_sims", "n_particles"}
    assert set(row["probs"]) == {"home", "draw", "away"}
    assert set(row["probs_se"]) == {"home", "draw", "away"}
    # (f): the closed set of four, and no fifth margin quantity
    assert matchboard.MARGIN_THRESHOLDS == (2, 3, 4)
    assert len(matchboard.ROW_FLOAT_FIELDS) == 14


def test_the_forbidden_vocabulary_is_absent_from_every_field_name():
    """(f) and the product line's standing rule, as a mechanical check on the
    field names rather than a promise in a docstring."""
    arrays = _spread_rows()
    row = matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS)[0]
    text = " ".join(sorted(row)).lower()
    for banned in ("odds", "price", "return", "over", "under", "btts",
                   "both_teams", "total_goals", "benchmark", "edge"):
        assert banned not in text, banned


# ==========================================================================
# 4. determinism
# ==========================================================================

def test_the_same_arrays_derive_the_same_bytes_twice():
    arrays = _spread_rows()
    once = leaguesim.canonical_json(
        matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS))
    twice = leaguesim.canonical_json(
        matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS))
    assert once == twice


# ==========================================================================
# 5. the render
# ==========================================================================

def _document(rows) -> dict:
    return {
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
        "rows": rows,
    }


def test_the_render_carries_the_no_claim_sentence_verbatim():
    """A7 (a): *in these terms and not softer ones*."""
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS)
    text = matchboard.render_markdown(_document(rows))
    assert matchboard.NO_CLAIM in text
    assert matchboard.NO_CLAIM == (
        "these numbers carry no accuracy claim; the claim is earned by the "
        "live scored record or not at all")
    # the law is ONE arm's
    assert "dc_native" in text
    # D11 v1.0.1 (A1): truncation at 10 goals, tail discarded
    assert "10 goals" in text and "D11 v1.0.1" in text
    # how many fixtures carried provisional widening
    assert "38" in text


def test_the_render_never_prints_a_probability_without_its_error():
    """The house rule: an interval whose method is not stated is a decoration,
    and a probability with no error beside it is worse.

    The table's first four cells name the fixture; every cell after them is a
    quantity, and every one of those carries its Monte-Carlo error.
    """
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS)
    text = matchboard.render_markdown(_document(rows))
    header = next(ln for ln in text.splitlines() if ln.startswith("| Fixture |"))
    assert [c.strip() for c in header.strip("|").split("|")] == [
        "Fixture", "Date", "Home", "Away", "P(home)", "P(draw)", "P(away)",
        "E margin", "P(margin 2+)", "P(margin 3+)", "P(margin 4+)"]

    table = [ln for ln in text.splitlines() if ln.startswith("| `2627:")]
    assert table, "the render carries no fixture row"
    for line in table:
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert len(cells) == 11, line
        for cell in cells[4:]:
            assert "±" in cell, f"a naked number on the matchboard: {cell!r}"
            assert re.fullmatch(r"[0-9]+\.[0-9]+ ± [0-9]+\.[0-9]+", cell), cell
    assert matchboard.SE_METHOD in text
    assert "cluster-by-particle" in matchboard.SE_METHOD


def test_the_render_states_the_provenance_of_the_rows_it_prints():
    """A7 (d): a surface derived from rows no pre-kickoff hash covers must say
    so, and must not call them anchored. Two different statements, never
    collapsed into one word."""
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS)
    doc = _document(rows)
    text = matchboard.render_markdown(doc)
    assert matchboard.ROWS_REPRODUCTION_NOTE in text
    assert matchboard.ROWS_ANCHORED_NOTE not in text
    assert "not anchored" in matchboard.ROWS_REPRODUCTION_NOTE

    anchored = matchboard.render_markdown(dict(doc, rows_provenance="anchored"))
    assert matchboard.ROWS_ANCHORED_NOTE in anchored
    assert matchboard.ROWS_REPRODUCTION_NOTE not in anchored


# ==========================================================================
# 6. the scorecard ledger — A7 (e)
# ==========================================================================

def test_the_uniform_baseline_is_the_pre_stated_arithmetic():
    """5/18 for a home or away result, 1/9 for a draw — pre-stated exactly, so
    the implementation reproduces arithmetic rather than defining it."""
    assert matchboard.uniform_rps("home") == pytest.approx(5 / 18, abs=1e-12)
    assert matchboard.uniform_rps("away") == pytest.approx(5 / 18, abs=1e-12)
    assert matchboard.uniform_rps("draw") == pytest.approx(1 / 9, abs=1e-12)
    assert round(matchboard.uniform_rps("home"), 6) == 0.277778
    assert round(matchboard.uniform_rps("draw"), 6) == 0.111111


def test_rps_is_this_projects_literal_over_the_ordered_outcomes():
    """`RPS = (1/(r-1)) sum_{i=1..r-1} (CP_i - CO_i)^2`, r = 3, over
    (home, draw, away)."""
    certain = {"home": 1.0, "draw": 0.0, "away": 0.0}
    assert matchboard.rps(certain, "home") == pytest.approx(0.0, abs=1e-12)
    assert matchboard.rps(certain, "away") == pytest.approx(1.0, abs=1e-12)
    assert matchboard.rps(certain, "draw") == pytest.approx(0.5, abs=1e-12)

    uniform = {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
    for outcome in ("home", "draw", "away"):
        assert matchboard.rps(uniform, outcome) == pytest.approx(
            matchboard.uniform_rps(outcome), abs=1e-12)

    # ORDER MATTERS: draw is the MIDDLE outcome, so a forecast that swaps draw
    # and away is a different forecast and must score differently.
    skewed = {"home": 0.5, "draw": 0.3, "away": 0.2}
    swapped = {"home": 0.5, "draw": 0.2, "away": 0.3}
    assert matchboard.rps(skewed, "away") != pytest.approx(
        matchboard.rps(swapped, "away"), abs=1e-9)


def _scored_board():
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS)
    return _document(rows)


def _ledger(*rows):
    """A results ledger for the synthetic season, resolved by SEASON'S OWN code.

    :func:`epl.season.resolve_ledger` is the one implementation of this
    project's bitemporal resolution — the same call the league table makes — so
    a scorecard built against this view is built against the same conflict
    rules, not against a second set written for the tests.
    """
    return season_mod.resolve_ledger(
        [{"observed_at": "2026-08-22T09:00:00",
          "date_played": FACTS[row["fixture_id"]]["date"], **row}
         for row in rows],
        identify=lambda row: str(row["fixture_id"]))


def _played(fixture_id="2627:alpha:bravo", hg=2, ag=0, **extra):
    return {"fixture_id": fixture_id, "hg": hg, "ag": ag, **extra}


def test_a_scorecard_row_carries_the_forecast_the_result_and_the_bundle():
    board = _scored_board()
    ledger = matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                       "home_goals": 2, "away_goals": 0,
                                       "matchweek": 1, "ingest": "manual/day1"}],
                              ledger=_ledger(_played(hg=2, ag=0)))
    assert len(ledger) == 1
    row = ledger[0]
    assert row["fixture_id"] == "2627:alpha:bravo"
    assert row["outcome"] == "home"
    assert row["realized_margin"] == 2
    assert row["matchweek"] == 1
    assert row["ingest"] == "manual/day1"
    # the forecast AS ISSUED, and the bundle that issued it
    assert row["probs"] == board["rows"][0]["probs"]
    assert row["season"] == "2026/27"
    assert row["cutoff"] == board["cutoff"]
    assert row["observed_by"] == board["observed_by"]
    assert row["run_digest"] == board["run_digest"]
    # A7 (d): a row citing a bundle whose rows are unanchored says so
    assert row["rows_provenance"] == "reproduction"
    # the two score columns, and no third
    assert row["rps"] == pytest.approx(
        matchboard.rps(row["probs"], "home"), abs=1e-12)
    assert row["rps_uniform"] == pytest.approx(5 / 18, abs=1e-12)
    assert not any("benchmark" in k for k in row), \
        "(f): no benchmark comparison column on this surface"


def test_a_draw_scores_against_the_middle_outcome_and_a_zero_margin():
    board = _scored_board()
    row = matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                    "home_goals": 1, "away_goals": 1,
                                    "matchweek": 1, "ingest": "x"}],
                           ledger=_ledger(_played(hg=1, ag=1)))[0]
    assert row["outcome"] == "draw"
    assert row["realized_margin"] == 0
    assert row["rps_uniform"] == pytest.approx(1 / 9, abs=1e-12)


def test_a_forecast_that_did_not_precede_the_kickoff_is_refused():
    """A7 (e): admissible ONLY if `cutoff` AND `observed_by` are at or before the
    fixture's kickoff as the season knew it. The World Cup edition's PIT
    discipline, restated for a league season — and fail-closed, because a ledger
    that silently drops the row it cannot justify is a ledger nobody can audit.
    """
    board = _scored_board()
    late = dict(board, observed_by="2026-08-25 00:00:00")   # kickoff 2026-08-21
    result = [{"fixture_id": "2627:alpha:bravo", "home_goals": 1,
               "away_goals": 0, "matchweek": 1, "ingest": "x"}]
    view = _ledger(_played(hg=1, ag=0))
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.score(late, result, ledger=view)
    assert "2627:alpha:bravo" in str(exc.value)
    assert "observed_by" in str(exc.value)

    # the CUTOFF is held to the same rule, on its own
    late_cutoff = dict(board, cutoff="2026-08-25 00:00:00")
    with pytest.raises(matchboard.MatchboardError):
        matchboard.score(late_cutoff, result, ledger=view)

    # POSITIVE CONTROL: the same result on the same day the season had the
    # kickoff is admissible, so the refusal above is about the ordering.
    assert matchboard.score(board, result,
                            ledger=view)[0]["date"] == "2026-08-21"


def test_a_result_for_a_fixture_the_matchboard_never_priced_is_refused():
    board = _scored_board()
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.score(board, [{"fixture_id": "2627:not:a_fixture",
                                  "home_goals": 0, "away_goals": 0,
                                  "matchweek": 1, "ingest": "x"}],
                         ledger=_ledger())
    assert "2627:not:a_fixture" in str(exc.value)


def test_a_result_the_season_ledger_does_not_carry_is_refused():
    """THE LEDGER IS THE SOURCE OF TRUTH for what was played (Codex r7 #4).

    Before this, `score` read the scoreline off the results file it was handed
    and checked only that the matchboard priced the fixture. So a fabricated
    result for a fixture nine months in the future — `99-(-7)`, matchweek and
    ingest both the empty string — became a scorecard row while the season's
    results ledger was still EMPTY, and the row it produced looked exactly like
    a real one. A scorecard is a READING of the ledger; it is never a second
    door a result can come through.
    """
    board = _scored_board()
    fabricated = {"fixture_id": "2627:alpha:bravo", "home_goals": 99,
                  "away_goals": -7, "matchweek": "", "ingest": ""}
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.score(board, [fabricated], ledger=_ledger())
    assert "2627:alpha:bravo" in str(exc.value)

    # ...and a well-formed result for a fixture the ledger has not reached is
    # refused for the same reason, naming the ledger.
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                  "home_goals": 2, "away_goals": 0,
                                  "matchweek": 1, "ingest": "manual/day1"}],
                         ledger=_ledger())
    assert "ledger" in str(exc.value)


def test_a_scorecard_row_that_disagrees_with_the_ledger_is_refused():
    """The ledger resolves; the scorecard reads. A row that scores a different
    scoreline than the season resolved is refused rather than filed beside it."""
    board = _scored_board()
    view = _ledger(_played(hg=2, ag=0))
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                  "home_goals": 3, "away_goals": 0,
                                  "matchweek": 1, "ingest": "x"}], ledger=view)
    assert "3-0" in str(exc.value) and "2-0" in str(exc.value)

    # POSITIVE CONTROL: the same row, agreeing, is admissible.
    assert matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                     "home_goals": 2, "away_goals": 0,
                                     "matchweek": 1, "ingest": "x"}],
                            ledger=view)[0]["realized_margin"] == 2


def test_a_result_the_ledger_has_since_withdrawn_is_not_scored():
    """`resolve_ledger`'s own conflict rule, not a second one written here: a
    score followed by a later `abandoned` is NOT a result, and the scorecard
    inherits that answer from the season rather than deciding it again."""
    board = _scored_board()
    view = _ledger(_played(hg=2, ag=0),
                   {"fixture_id": "2627:alpha:bravo", "status": "abandoned",
                    "observed_at": "2026-08-23T09:00:00"})
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                  "home_goals": 2, "away_goals": 0,
                                  "matchweek": 1, "ingest": "x"}], ledger=view)
    assert "abandoned" in str(exc.value)


def test_a_goal_count_that_is_not_one_is_refused_at_the_door():
    """`epl.season.goal_count` is THE definition (finite, non-negative,
    integral), applied here rather than re-spelled."""
    board = _scored_board()
    view = _ledger(_played(hg=2, ag=0))
    good = {"fixture_id": "2627:alpha:bravo", "home_goals": 2, "away_goals": 0,
            "matchweek": 1, "ingest": "x"}
    for bad in ({"away_goals": -7}, {"home_goals": 1.9}, {"home_goals": "two"},
                {"home_goals": float("nan")}, {"away_goals": None}):
        with pytest.raises(matchboard.MatchboardError) as exc:
            matchboard.score(board, [{**good, **bad}], ledger=view)
        assert "2627:alpha:bravo" in str(exc.value), bad


# ==========================================================================
# 7. the derived-artifact naming convention (A7 (c))
# ==========================================================================

def test_a_derived_artifact_is_found_however_deep_it_is_buried(tmp_path):
    """Codex r7 #5(a): the scan read only a directory's IMMEDIATE children.

    A7 (c) FAILs a bundle that CONTAINS a derived artifact, and "contains" is
    not "lists": one subdirectory was enough to make a derivation inside a
    bundle invisible to the refusal that exists to find it.
    """
    bundle = tmp_path / "bundle"
    (bundle / "nested-derived" / "deeper").mkdir(parents=True)
    top = matchboard.derived_filename("2026/27", "2026-08-21", "json")
    buried = matchboard.derived_filename("2026/27", "2026-08-21", "md")
    (bundle / top).write_text("{}")
    (bundle / "nested-derived" / "deeper" / buried).write_text("# derived\n")
    (bundle / "rows_dc_native.npz").write_text("not really an npz")

    found = matchboard.derived_artifacts_in(bundle)
    assert found == [top, f"nested-derived/deeper/{buried}"]
    # POSITIVE CONTROL: it is not simply listing everything under the bundle
    assert "rows_dc_native.npz" not in found


def test_the_derived_naming_convention_is_recognised_in_both_directions():
    assert matchboard.derived_filename("2026/27", "2026-08-21", "json") == \
        "epl_matchboard_2026_27_2026-08-21_derived.json"
    assert matchboard.derived_filename("2026/27", "2026-08-21", "md") == \
        "epl_matchboard_2026_27_2026-08-21_derived.md"
    for name in ("epl_matchboard_2026_27_2026-08-21_derived.json",
                 "epl_matchboard_2026_27_2026-08-21_derived.md"):
        assert matchboard.is_derived_name(name), name
    for name in ("matchboard_dc_native.json", "matchboard.md",
                 "epl_matchboard_2026_27_2026-08-21.json",
                 "issuance.json", "rows_dc_native.npz"):
        assert not matchboard.is_derived_name(name), name


def test_derived_artifacts_in_a_directory_are_listed(tmp_path):
    (tmp_path / "matchboard.md").write_text("x")
    (tmp_path / "epl_matchboard_2026_27_2026-08-21_derived.json").write_text("{}")
    assert matchboard.derived_artifacts_in(tmp_path) == [
        "epl_matchboard_2026_27_2026-08-21_derived.json"]
    assert matchboard.derived_artifacts_in(tmp_path / "nope") == []


def test_a_derived_document_says_so_on_its_first_line(tmp_path):
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS)
    doc = matchboard.as_derived(_document(rows), source_bundle="/some/bundle",
                               derived_at="2026-08-25T10:00:00",
                               recorded_hashes={"digests": {"dc_native": "3a" * 32}})
    assert doc["derived"] is True
    assert doc["source_bundle"] == "/some/bundle"
    assert doc["derived_at"] == "2026-08-25T10:00:00"
    assert doc["source_recorded_hashes"] == {"digests": {"dc_native": "3a" * 32}}

    first = matchboard.render_markdown(doc).splitlines()[0]
    assert "derived" in first.lower()
    assert "not part of" in first.lower()


# ==========================================================================
# 8. the preserved MW0 bundle — the pre-stated control, on the COUNTS
# ==========================================================================

@pytest.mark.skipif(not COMMITTED_OPENER.exists(),
                    reason="the preserved opener bundle is not present")
def test_the_MW0_control_reproduces_on_the_counts_not_on_a_rendered_string():
    """A7 *What is pre-stated* 1, asserted the way the amendment insists.

    The session's earlier figure `A 0.0743` is `0.074350` TRUNCATED and the draw
    cell sits exactly on the four-place boundary, so a test that string-matched
    either rendering would have failed correct code. The control is the counts,
    and the probabilities to 1e-9.
    """
    board = matchboard.derive(COMMITTED_OPENER)
    record = json.loads((COMMITTED_OPENER / "issuance.json").read_text())
    assert board["n_fixtures"] == record["n_unplayed"] == 380
    assert board["n_sims"] == record["n_sims"] == 20000
    assert board["n_particles"] == 1000
    assert board["schema_version"] == "epl-matchboard-1"
    assert board["arm"] == "dc_native"
    assert board["run_digest"] == record["digests"]["dc_native"]

    row = next(r for r in board["rows"]
               if r["fixture_id"] == "2627:arsenal:coventry")
    assert row["fixture_ordinal"] == 5
    n = row["n_sims"]
    assert n == 20000 and row["n_particles"] == 1000
    # the counts, exactly
    assert round(row["probs"]["home"] * n) == 15278
    assert round(row["probs"]["draw"] * n) == 3235
    assert round(row["probs"]["away"] * n) == 1487
    assert (round(row["probs"]["home"] * n) + round(row["probs"]["draw"] * n)
            + round(row["probs"]["away"] * n)) == 20000
    # ...and the probabilities to 1e-9, as exact ratios
    assert row["probs"]["home"] == pytest.approx(7639 / 10000, abs=1e-9)
    assert row["probs"]["draw"] == pytest.approx(647 / 4000, abs=1e-9)
    assert row["probs"]["away"] == pytest.approx(1487 / 20000, abs=1e-9)
    assert row["probs_se"]["home"] == pytest.approx(0.003511, abs=5e-7)
    assert row["probs_se"]["draw"] == pytest.approx(0.002800, abs=5e-7)
    assert row["probs_se"]["away"] == pytest.approx(0.002006, abs=5e-7)

    assert row["e_margin"] == pytest.approx(2.642600, abs=1e-9)
    assert row["e_margin_se"] == pytest.approx(0.020452, abs=5e-7)
    assert row["p_marg_ge2"] == pytest.approx(2451 / 4000, abs=1e-9)
    assert row["p_marg_ge3"] == pytest.approx(8611 / 20000, abs=1e-9)
    assert row["p_marg_ge4"] == pytest.approx(2919 / 10000, abs=1e-9)
    assert row["p_marg_ge2_se"] == pytest.approx(0.004215, abs=5e-7)
    assert row["p_marg_ge3_se"] == pytest.approx(0.004351, abs=5e-7)
    assert row["p_marg_ge4_se"] == pytest.approx(0.004036, abs=5e-7)

    # the invariants, on all 380 rows of a real run
    assert [r["fixture_ordinal"] for r in board["rows"]] == list(range(380))
    for r in board["rows"]:
        p = r["probs"]
        assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-9
        assert r["p_marg_ge2"] >= r["p_marg_ge3"] >= r["p_marg_ge4"]
        assert r["n_sims"] == board["n_sims"]


@pytest.mark.skipif(not COMMITTED_OPENER.exists(),
                    reason="the preserved opener bundle is not present")
def test_the_MW0_rows_are_reported_as_reproducible_and_never_as_anchored():
    """A7 (d): the law is anchored pre-kickoff; the ROWS are not, because
    `data/` is not in git and the record is `epl-issuance-1` with no
    `sidecar_digests`. The derivation must inherit both statements separately.
    """
    board = matchboard.derive(COMMITTED_OPENER)
    assert board["rows_provenance"] == "reproduction"
    assert board["effective_posterior_hash"] == (
        "b87c4a17cd4ce867a6e92447d214ba3454dcc3376c2da85b85dbc09862cb1b61")
    assert board["run_digest"] == (
        "3a40110cd41286c42125322b9f90f36387d27e5d212992426eb78a2de0b3eb8a")
    text = matchboard.render_markdown(board)
    assert matchboard.ROWS_REPRODUCTION_NOTE in text
    assert matchboard.ROWS_ANCHORED_NOTE not in text


# ==========================================================================
# 9. A7 (d) — TWO KINDS OF PROVENANCE, AND THE TEXT SAYS BOTH
# ==========================================================================

def _law_anchor(pre_kickoff=True):
    return {
        "cutoff": "2026-08-21 00:00:00",
        "pre_kickoff": bool(pre_kickoff),
        "hashes": [
            {"name": "effective_posterior_hash", "hash": "b8" * 32,
             "file": "reports/epl_sim_issuance_2026-08-21.md",
             "commit": "9478e7111a0f2e473deef2496b1e273834d51d6f",
             "committed_at": ("2026-08-19T16:15:58+08:00" if pre_kickoff
                              else "2026-09-01T10:00:00+08:00")},
            {"name": "run_digest", "hash": "3a" * 32,
             "file": "reports/epl_sim_issuance_2026-08-21.md",
             "commit": "9478e7111a0f2e473deef2496b1e273834d51d6f",
             "committed_at": ("2026-08-19T16:15:58+08:00" if pre_kickoff
                              else "2026-09-01T10:00:00+08:00")},
        ],
    }


def _derived(law_anchor):
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS)
    doc = dict(_document(rows), law_anchor=law_anchor)
    return matchboard.as_derived(doc, source_bundle="/bundle",
                                 derived_at="2026-08-25T10:00:00",
                                 recorded_hashes={})


def test_a_derived_render_says_the_law_is_anchored_and_the_rows_are_not():
    """A7 (d): *A derived artifact's own text, and any scorecard row that cites
    it, must say both — and must not call the rows anchored.*

    It would have been easy, and wrong, to write that the derivation "inherits
    pre-kickoff provenance through the hash chain". Part of it does. The rows do
    not, and the two get different words.
    """
    text = matchboard.render_markdown(_derived(_law_anchor(True)))
    assert matchboard.LAW_ANCHORED_NOTE in text
    assert matchboard.LAW_UNANCHORED_NOTE not in text
    # the rows keep their own, weaker sentence, in the same document
    assert matchboard.ROWS_REPRODUCTION_NOTE in text
    assert matchboard.ROWS_ANCHORED_NOTE not in text
    # and the anchor is CHECKABLE: which file, which commit, when
    assert "9478e7111a0f2e473deef2496b1e273834d51d6f" in text
    assert "reports/epl_sim_issuance_2026-08-21.md" in text
    assert "2026-08-19T16:15:58+08:00" in text


def test_a_law_recorded_only_after_the_cutoff_is_not_called_pre_kickoff():
    """The positive control: the anchored sentence is not decoration. A hash
    first written into a tracked file AFTER the cutoff anchors nothing about a
    forecast made before it."""
    text = matchboard.render_markdown(_derived(_law_anchor(False)))
    assert matchboard.LAW_UNANCHORED_NOTE in text
    assert matchboard.LAW_ANCHORED_NOTE not in text
    assert matchboard.ROWS_REPRODUCTION_NOTE in text


def test_a_bundle_matchboard_makes_no_law_anchor_claim_at_all():
    """A sidecar written by the run that issued it has no git history to appeal
    to, so it claims neither — silence rather than a sentence nobody checked."""
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS)
    text = matchboard.render_markdown(_document(rows))
    assert matchboard.LAW_ANCHORED_NOTE not in text
    assert matchboard.LAW_UNANCHORED_NOTE not in text


def test_a_scorecard_row_citing_a_derived_board_records_both_provenances():
    """A7 (e): the row records enough for a reader to check the ordering rather
    than trust it — and it says what the ROWS have, in the word that is true."""
    board = _derived(_law_anchor(True))
    row = matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                    "home_goals": 3, "away_goals": 0,
                                    "matchweek": 1, "ingest": "manual/day1"}],
                           ledger=_ledger(_played(hg=3, ag=0)))[0]
    assert row["rows_provenance"] == "reproduction"
    assert row["law_provenance"] == "anchored-pre-kickoff"
    assert row["source_bundle"] == "/bundle"

    late = _derived(_law_anchor(False))
    row = matchboard.score(late, [{"fixture_id": "2627:alpha:bravo",
                                   "home_goals": 3, "away_goals": 0,
                                   "matchweek": 1, "ingest": "x"}],
                           ledger=_ledger(_played(hg=3, ag=0)))[0]
    assert row["law_provenance"] == "not-shown-anchored"


def test_the_law_anchor_compares_instants_and_not_two_wall_clocks():
    """Codex r7 #6: `_committed_by` dropped the git stamp's offset and compared
    the two local times as if they were one clock.

    That is not a comparison. A commit made nearly thirteen hours AFTER the
    cutoff passed, and one made thirteen hours BEFORE it was refused — and both
    are reachable, because `TZ` is whatever the committing machine says it is
    and `git commit --date` sets the author stamp to any offset you like. An
    anchor a timezone can move is not an anchor.

    The cutoff is a naive timestamp written in the terms the competition is
    written in — an English league's kickoff days are UK local dates — so it is
    resolved through `Europe/London`, named in `simcli.SEASON_TIMEZONE` rather
    than assumed. `2026-08-21 00:00:00` London is `2026-08-20T23:00Z`, August
    being BST.
    """
    from zoneinfo import ZoneInfo

    from epl import simcli

    assert simcli.SEASON_TIMEZONE == ZoneInfo("Europe/London")
    cutoff = "2026-08-21 00:00:00"
    bound = pd.Timestamp(cutoff).tz_localize(simcli.SEASON_TIMEZONE)
    assert str(bound.tz_convert("UTC")) == "2026-08-20 23:00:00+00:00"

    # Codex's two probes, each with the instant it really is
    late = "2026-08-20T23:59:00-12:00"                  # 2026-08-21T11:59Z
    early = "2026-08-21T00:01:00+14:00"                 # 2026-08-20T10:01Z
    assert pd.Timestamp(late) > bound and pd.Timestamp(early) < bound
    assert simcli._committed_by(late, cutoff) is False
    assert simcli._committed_by(early, cutoff) is True

    # the MW0 stamp — both of the opener's are this one — still anchors
    assert simcli._committed_by("2026-08-19T16:15:58+08:00", cutoff) is True
    # ...and a hash with no commit anchors nothing
    assert simcli._committed_by(None, cutoff) is False

    # a naive stamp is read on the season's clock, which is the only reading
    # that makes the two sides comparable at all
    assert simcli._committed_by("2026-08-21 00:00:00", cutoff) is True
    assert simcli._committed_by("2026-08-21 00:00:01", cutoff) is False


@pytest.mark.skipif(not COMMITTED_OPENER.exists(),
                    reason="the preserved opener bundle is not present")
def test_the_MW0_law_anchor_is_the_commit_the_ledger_entered():
    """A7 (d) entered `9478e71` and REFUSED `426eed7` — an object that is not in
    this repository. The anchor is computed from this history, so the claim is
    checkable by whoever reads it.

    The amendment ledger ALSO carries the posterior hash, at `5201eac` on
    2026-08-25 — four days after the cutoff. The earliest introducing commit is
    the anchor; a later mention of the same hash cannot become one.
    """
    from epl import simcli

    record = json.loads((COMMITTED_OPENER / "issuance.json").read_text())
    anchor = simcli.law_anchor(record)
    if anchor is None:                                      # pragma: no cover
        pytest.skip("this checkout has no git history for reports/")
    assert anchor["pre_kickoff"] is True
    assert {h["name"] for h in anchor["hashes"]} == {
        "effective_posterior_hash", "run_digest"}
    for entry in anchor["hashes"]:
        assert entry["commit"].startswith("9478e711"), entry
        assert entry["file"] == "reports/epl_sim_issuance_2026-08-21.md", entry
        assert entry["committed_at"].startswith("2026-08-19"), entry
    assert anchor["cutoff"] == record["cutoff"]


def test_a_result_with_no_matchweek_or_no_ingest_is_refused():
    """A7 (e): *the ledger is append-only, and each row records the matchweek and
    the ingest that supplied the result.*

    A row filed with neither cannot do what a per-matchweek append-only ledger
    is for — nobody can say which matchweek it belongs to or which ingest put it
    there — so it is refused at the door rather than written with two nulls in
    it and discovered later.
    """
    board = _scored_board()
    good = {"fixture_id": "2627:alpha:bravo", "home_goals": 1, "away_goals": 0,
            "matchweek": 1, "ingest": "manual/day1"}
    view = _ledger(_played(hg=1, ag=0))
    assert matchboard.score(board, [good], ledger=view)[0]["matchweek"] == 1

    for missing in ("matchweek", "ingest"):
        holed = {k: v for k, v in good.items() if k != missing}
        with pytest.raises(matchboard.MatchboardError) as exc:
            matchboard.score(board, [holed], ledger=view)
        assert missing in str(exc.value), missing
        assert "2627:alpha:bravo" in str(exc.value)
        # ...and present-but-null is the same absence wearing a value
        with pytest.raises(matchboard.MatchboardError):
            matchboard.score(board, [{**good, missing: None}], ledger=view)
        # ...as is present-but-EMPTY, which is what a hand-written results file
        # produces when a column was left blank
        with pytest.raises(matchboard.MatchboardError) as exc:
            matchboard.score(board, [{**good, missing: ""}], ledger=view)
        assert missing in str(exc.value), missing
        with pytest.raises(matchboard.MatchboardError):
            matchboard.score(board, [{**good, missing: "   "}], ledger=view)


def test_no_market_vocabulary_reaches_the_render_or_the_scorecard():
    """A7 (f) and the product line's standing rule, checked mechanically on the
    two surfaces a reader actually sees rather than promised in a docstring."""
    board = _scored_board()
    text = matchboard.render_markdown(board).lower()
    row = matchboard.score(board, [{"fixture_id": "2627:alpha:bravo",
                                    "home_goals": 1, "away_goals": 0,
                                    "matchweek": 1, "ingest": "x"}],
                           ledger=_ledger(_played(hg=1, ag=0)))[0]
    banned = ("odds", "payout", "stake", "bookmaker", "handicap",
              "correct score", "both teams to score", "btts", "benchmark",
              "total goals", "over/under")
    for word in banned:
        assert word not in text, word
        assert word not in " ".join(sorted(row)).lower().replace("_", " "), word
    # POSITIVE CONTROL: the scan is not vacuous — it finds a word that IS there.
    assert "margin" in text


def test_a_particle_grid_the_ENGINE_would_refuse_is_refused_here_too():
    """Codex r7 #7: the rows are not re-run, so nothing else asks whether they
    could have come out of a `SimPlan` at all — and every ± on the surface is
    computed as if they had.

    `epl.leaguesim.check_particle_grid` is the engine's own rule, called rather
    than restated. The single-particle case is the one that matters:
    `cluster_se` returns exactly `0.0` for one cluster, so the board would
    publish a full table of probabilities with a stated Monte-Carlo error of
    ZERO in every cell — the one value that cannot be right.
    """
    def arrays(particle):
        n = len(particle)
        scorelines = np.zeros((n, 1, 2), np.int8)
        scorelines[:n // 2] = (2, 0)
        return _arrays(scorelines, particle, [0])

    ids, facts = ("2627:alpha:bravo",), {
        "2627:alpha:bravo": FACTS["2627:alpha:bravo"]}

    # what the ENGINE refuses, named by what it says
    for label, particle in (("one particle", [0, 0, 0, 0]),
                            ("N not a multiple of S", [0, 0, 1, 1, 2]),
                            ("one season per particle", [0, 1])):
        with pytest.raises(leaguesim.SimError):
            leaguesim.check_particle_grid(len(particle), len(set(particle)))
        with pytest.raises(matchboard.MatchboardError) as exc:
            matchboard.derive_rows(arrays(particle), fixture_ids=ids, facts=facts)
        assert "grid" in str(exc.value), label

    # ...and UNEQUAL COUNTS, which the engine gets for free from the stratified
    # `i mod S` and therefore never checks, so this one is only checked here.
    assert leaguesim.check_particle_grid(4, 2) is None
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.derive_rows(arrays([0, 0, 0, 1]), fixture_ids=ids, facts=facts)
    assert "unequally" in str(exc.value)

    # POSITIVE CONTROL: the grid the engine DOES produce derives, and its
    # standard error is not zero — which is what the refusals are protecting.
    rows = matchboard.derive_rows(arrays([0, 0, 1, 1]), fixture_ids=ids,
                                  facts=facts)
    assert rows[0]["n_particles"] == 2
    assert rows[0]["probs_se"]["home"] > 0.0


def test_two_columns_claiming_one_fixture_are_refused():
    """A rows file whose ordinals repeat is corrupt, and the count check cannot
    see it: 380 columns with one ordinal twice and another missing still prices
    380 fixtures. Two rows for one fixture is the visible half; a fixture the
    run priced and the board never mentions is the half that matters.
    """
    scorelines = np.zeros((4, 3, 2), np.int8)
    arrays = _arrays(scorelines, [0, 0, 1, 1], [0, 2, 2])
    with pytest.raises(matchboard.MatchboardError) as exc:
        matchboard.derive_rows(arrays, fixture_ids=SEASON_IDS, facts=FACTS)
    assert "2" in str(exc.value)
    assert "2627:echo:foxtrot" in str(exc.value)


def test_the_matchboard_reads_no_clock_and_moving_the_clock_proves_it(monkeypatch):
    """The verifier's one surviving seed: a wall-clock read planted in the
    renderer left every test green. Same disease `test_limitations_note_is_
    byte_identical_across_runs` had, one file over, and the same cure: do not
    string-match today's date (that guard false-alarms the day a kickoff equals
    the wall clock) — MOVE the clock and require identical bytes.

    The swap goes through ``sys.modules`` as well as the module attribute, so a
    function-local ``import time`` — which a module-attribute monkeypatch never
    sees — is intercepted too. ``derived_at`` is an INPUT here; the boundary
    (the CLI) may read a clock, the library may not.
    """
    import datetime as real_datetime
    import sys
    import time as real_time

    doc = _derived(_law_anchor(True))
    before_md = matchboard.render_markdown(doc)
    before_js = leaguesim.canonical_json(doc)

    class _FrozenTime:
        @staticmethod
        def time():
            return 0.0

        @staticmethod
        def monotonic():
            return 0.0

        @staticmethod
        def perf_counter():
            return 0.0

        @staticmethod
        def strftime(fmt, t=None):
            return "FROZEN"

        @staticmethod
        def gmtime(secs=None):
            return real_time.gmtime(0)

        @staticmethod
        def localtime(secs=None):
            return real_time.localtime(0)

    class _FrozenDatetime:
        timezone = real_datetime.timezone
        timedelta = real_datetime.timedelta

        class datetime(real_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(1970, 1, 1)

            @classmethod
            def utcnow(cls):
                return cls(1970, 1, 1)

        class date(real_datetime.date):
            @classmethod
            def today(cls):
                return cls(1970, 1, 1)

    monkeypatch.setitem(sys.modules, "time", _FrozenTime)
    monkeypatch.setitem(sys.modules, "datetime", _FrozenDatetime)
    monkeypatch.setattr(matchboard, "time", _FrozenTime, raising=False)
    monkeypatch.setattr(matchboard, "datetime", _FrozenDatetime, raising=False)

    assert matchboard.render_markdown(doc) == before_md, (
        "matchboard.md changed when the clock moved — the renderer is reading "
        "a wall clock, so the same derivation would not reproduce tomorrow")
    assert leaguesim.canonical_json(doc) == before_js


def test_a_backdated_author_date_cannot_anchor_a_hash_pre_kickoff(tmp_path):
    """A7 (d)'s anchor is only as strong as the weaker of git's two dates.

    ``GIT_AUTHOR_DATE`` survives rebase and amend and is trivially settable, so
    a hash introduced AFTER the cutoff can wear a pre-cutoff author date at one
    keystroke. The committer date is rewritten by every history edit, which is
    exactly why it must ALSO be at or before the cutoff: an anchor may only be
    as old as the NEWER of the two stamps. Neither is cryptographic — the
    ledger says so — but the check must use the stronger of what git has.
    """
    import subprocess

    from epl import simcli

    posterior, run_digest = "ab" * 32, "cd" * 32
    root = tmp_path / "repo"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "x.md").write_text(
        f"posterior {posterior}\nrun {run_digest}\n")

    def _git(*args, **env_extra):
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
               "HOME": str(tmp_path), **env_extra}
        subprocess.run(["git", *args], cwd=root, check=True,
                       capture_output=True, env={**__import__("os").environ,
                                                 **env})

    _git("init", "-q")
    _git("add", "reports/x.md")
    # authored BEFORE the cutoff, committed AFTER it: the forgeable stamp says
    # pre-kickoff, the history-honest one says otherwise.
    _git("commit", "-q", "-m", "x",
         GIT_AUTHOR_DATE="2026-08-19T12:00:00+08:00",
         GIT_COMMITTER_DATE="2026-09-01T12:00:00+08:00")

    record = {"cutoff": "2026-08-21 00:00:00",
              "effective_posterior_hash": posterior,
              "digests": {"dc_native": run_digest}}
    anchor = simcli.law_anchor(record, repo_root=root, pathspec="reports")
    assert anchor is not None
    assert anchor["pre_kickoff"] is False, (
        "a post-cutoff committer date must refuse the anchor no matter what "
        "the author date claims")
