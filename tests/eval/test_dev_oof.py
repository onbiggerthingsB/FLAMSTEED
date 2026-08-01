"""Tests for the V5 dev OOF walk — src/wcmodel/eval/oof.py + the runner.

Two classes of guarantee, both load-bearing for the transfer w makes from
the dev slate to the scored pools:

* the ARM BLOCK is complete and internally coherent (w=0 IS the incumbent,
  w=1 IS the de-vigged book, 46 arms exactly) — otherwise the selection is
  comparing candidates that were not all computed the same way;
* the walk is OUT OF FOLD — every row's training_cutoff is its own
  issuance instant, strictly before kickoff, and a fact dated after the
  cutoff cannot move the forecast.
"""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wcmodel.eval.blend import W_GRID, blend_arm
from wcmodel.eval.implied import OA_DEVIG_METHODS, oa_devig
from wcmodel.eval.oof import (
    DC_ARM,
    ELO_ARM,
    OofPricingError,
    book_1x2,
    expected_arms,
    ledger_rows,
    odds_arm,
    price_fixture,
)
from wcmodel.model.draw_api import FixtureCtx, grid_one_x_two, production_grid

from tests.model.conftest import fit_compact_real_posterior

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def runner():
    sys.path.insert(0, str(_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "oa_dev_oof", _ROOT / "scripts" / "oa_dev_oof.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oa_dev_oof"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def real_posterior(tmp_path_factory):
    return fit_compact_real_posterior(tmp_path_factory.mktemp("oof_store"))


@pytest.fixture(scope="module")
def ctx(real_posterior):
    teams = sorted(real_posterior.teams)
    return FixtureCtx(home=teams[0], away=teams[1])


class _Ordlogit:
    """A stand-in head: predict_1x2 only reads the fitted params, and the
    arm's own maths is covered by tests/eval/test_elo_ordlogit.py."""
    c1, s, b_elo, b_hfa = 0.0, 1.0, 1.0, 0.2
    n_hfa_minority, elo_edge_sd = 10, 100.0


# --------------------------------------------------------- the arm block
def test_expected_arms_is_46_derived_not_listed():
    arms = expected_arms(covered=True)
    assert len(arms) == 46 == 2 + len(OA_DEVIG_METHODS) * (1 + len(W_GRID))
    assert set(arms) >= {DC_ARM, ELO_ARM}
    for method in OA_DEVIG_METHODS:
        assert odds_arm(method) in arms
        assert blend_arm(method, 0.0) in arms and blend_arm(method, 1.0) in arms
    assert expected_arms(covered=False) == (DC_ARM, ELO_ARM)


def test_odds_arm_rejects_a_non_oa_method():
    with pytest.raises(ValueError, match="not in the OA set"):
        odds_arm("power")


def test_book_1x2_is_keyed_never_positional():
    prices = {"home": 2.0, "draw": 4.0, "away": 4.0}
    got = book_1x2(prices, method="multiplicative")
    want = oa_devig([2.0, 4.0, 4.0], method="multiplicative")
    assert got == pytest.approx(dict(zip(("home", "draw", "away"), want)))
    # swapping the LABELS swaps the probabilities — proof the mapping is by
    # key, so an API/store home-away flip cannot silently invert a forecast
    flipped = book_1x2({"home": 4.0, "draw": 4.0, "away": 2.0},
                       method="multiplicative")
    assert flipped["away"] == pytest.approx(got["home"])


def test_priced_block_is_complete_and_coherent(real_posterior, ctx):
    prices = {"home": 2.10, "draw": 3.30, "away": 3.60}
    priced = price_fixture(
        posterior=real_posterior, fixture_ctx=ctx, elo_home=1600.0,
        elo_away=1500.0, hfa=1.0, ordlogit_params=_Ordlogit(),
        book_prices=prices)
    assert sorted(priced) == sorted(expected_arms(covered=True))
    for arm, p in priced.items():
        assert sum(p.values()) == pytest.approx(1.0, abs=1e-9), arm


def test_w0_is_the_incumbent_and_w1_is_the_book(real_posterior, ctx):
    prices = {"home": 2.10, "draw": 3.30, "away": 3.60}
    priced = price_fixture(
        posterior=real_posterior, fixture_ctx=ctx, elo_home=1600.0,
        elo_away=1500.0, hfa=1.0, ordlogit_params=_Ordlogit(),
        book_prices=prices)
    incumbent = grid_one_x_two(production_grid(real_posterior, ctx))
    for method in OA_DEVIG_METHODS:
        # w=0: the per-draw identity makes the blend the incumbent exactly
        at0 = priced[blend_arm(method, 0.0)]
        for k in ("home", "draw", "away"):
            assert at0[k] == pytest.approx(incumbent[k], abs=1e-12), \
                f"{method} w=0 must BE dev_dc"
        # w=1: reproduces the de-vigged book through the finalized map
        at1 = priced[blend_arm(method, 1.0)]
        book = priced[odds_arm(method)]
        for k in ("home", "draw", "away"):
            assert at1[k] == pytest.approx(book[k], abs=1e-6), \
                f"{method} w=1 must reproduce dev_odds_{method}"


def test_odds_absent_fixture_gets_only_the_two_free_arms(real_posterior, ctx):
    priced = price_fixture(
        posterior=real_posterior, fixture_ctx=ctx, elo_home=1600.0,
        elo_away=1500.0, hfa=0.0, ordlogit_params=_Ordlogit(),
        book_prices=None)
    assert sorted(priced) == sorted(expected_arms(covered=False))


def test_unreachable_book_is_a_refusal_not_a_quiet_demotion(real_posterior,
                                                            ctx):
    # A draw probability far above what the bounded map can produce: the
    # fixture HAS a quote, so reporting it as uncovered would misstate the
    # analysed population — it must raise.
    with pytest.raises(OofPricingError, match="not reachable"):
        price_fixture(
            posterior=real_posterior, fixture_ctx=ctx, elo_home=1600.0,
            elo_away=1500.0, hfa=1.0, ordlogit_params=_Ordlogit(),
            book_prices={"home": 100.0, "draw": 1.01, "away": 100.0})


# ------------------------------------------------------------ ledger rows
def _fixture():
    return {"fixture_id": "f1", "pool": "UEFA Nations League",
            "date": "2024-09-05", "home": "A", "away": "B",
            "kickoff_utc": pd.Timestamp("2024-09-05T19:00:00Z")}


def test_only_odds_derived_arms_carry_the_snapshot_hash():
    priced = {DC_ARM: {"home": .5, "draw": .3, "away": .2},
              ELO_ARM: {"home": .4, "draw": .3, "away": .3},
              odds_arm("shin"): {"home": .45, "draw": .3, "away": .25}}
    t = datetime(2024, 9, 5, 9, tzinfo=timezone.utc)
    rows = ledger_rows(fixture=_fixture(), priced=priced, t_issue=t,
                       training_cutoff=t, issued_git="deadbeef",
                       odds_snapshot_hash="abc123")
    by_arm = {r["arm"]: r for r in rows}
    assert by_arm[DC_ARM]["odds_snapshot_hash"] is None
    assert by_arm[ELO_ARM]["odds_snapshot_hash"] is None
    assert by_arm[odds_arm("shin")]["odds_snapshot_hash"] == "abc123"


def test_odds_arm_without_provenance_is_refused():
    priced = {odds_arm("shin"): {"home": .45, "draw": .3, "away": .25}}
    t = datetime(2024, 9, 5, 9, tzinfo=timezone.utc)
    with pytest.raises(OofPricingError, match="unauditable"):
        ledger_rows(fixture=_fixture(), priced=priced, t_issue=t,
                    training_cutoff=t, issued_git="x",
                    odds_snapshot_hash=None)


# --------------------------------------------------- out-of-fold discipline
def test_t_issue_is_0900z_on_the_venue_local_matchday(runner):
    t = runner.t_issue_for("2024-09-05")
    assert (t.hour, t.minute, t.second) == (9, 0, 0)
    assert t.tzinfo is timezone.utc and t.date().isoformat() == "2024-09-05"


def test_every_emitted_row_is_out_of_fold(runner):
    """training_cutoff == t_issue < kickoff, per row — the information-set
    rule the ledger enforces, asserted here at the producer too."""
    t = runner.t_issue_for("2024-09-05")
    rows = ledger_rows(
        fixture=_fixture(),
        priced={DC_ARM: {"home": .5, "draw": .3, "away": .2}},
        t_issue=t, training_cutoff=t, issued_git="x",
        odds_snapshot_hash=None)
    for r in rows:
        assert r["training_cutoff"] == r["t_issue"]
        assert r["t_issue"] < pd.Timestamp(r["kickoff_utc"]).to_pydatetime()


def test_match_level_panel_pivots_and_labels_outcomes(runner):
    panel = pd.DataFrame([
        # one match, two team rows (the panel's shape)
        {"match_id": "m1", "date": pd.Timestamp("2024-01-01"), "team": "A",
         "opponent": "B", "is_home": True, "neutral": False, "elo_pre": 1600.0,
         "home_team": "A", "away_team": "B", "home_score": 2, "away_score": 1,
         "in_feature_window": True},
        {"match_id": "m1", "date": pd.Timestamp("2024-01-01"), "team": "B",
         "opponent": "A", "is_home": False, "neutral": False, "elo_pre": 1500.0,
         "home_team": "A", "away_team": "B", "home_score": 2, "away_score": 1,
         "in_feature_window": True},
        # out of the frozen window -> excluded
        {"match_id": "m0", "date": pd.Timestamp("1900-01-01"), "team": "A",
         "opponent": "B", "is_home": True, "neutral": True, "elo_pre": 1500.0,
         "home_team": "A", "away_team": "B", "home_score": 0, "away_score": 0,
         "in_feature_window": False},
        {"match_id": "m0", "date": pd.Timestamp("1900-01-01"), "team": "B",
         "opponent": "A", "is_home": False, "neutral": True, "elo_pre": 1500.0,
         "home_team": "A", "away_team": "B", "home_score": 0, "away_score": 0,
         "in_feature_window": False},
    ])
    out = runner.match_level_panel(panel)
    assert list(out["match_id"]) == ["m1"]          # window respected
    row = out.iloc[0]
    assert row.elo_h == 1600.0 and row.elo_a == 1500.0
    assert row.hfa == 1.0 and row.outcome == "home"


def test_neutral_fixture_gets_hfa_zero(runner):
    panel = pd.DataFrame([
        {"match_id": "m1", "date": pd.Timestamp("2024-01-01"), "team": "A",
         "opponent": "B", "is_home": True, "neutral": True, "elo_pre": 1600.0,
         "home_team": "A", "away_team": "B", "home_score": 1, "away_score": 1,
         "in_feature_window": True},
        {"match_id": "m1", "date": pd.Timestamp("2024-01-01"), "team": "B",
         "opponent": "A", "is_home": False, "neutral": True, "elo_pre": 1500.0,
         "home_team": "A", "away_team": "B", "home_score": 1, "away_score": 1,
         "in_feature_window": True},
    ])
    out = runner.match_level_panel(panel)
    assert out.iloc[0].hfa == 0.0 and out.iloc[0].outcome == "draw"


# --------------------------------------------------------- odds provenance
def _snapshot_blob(tmp_path, digest, *, home, away, home_price, draw_price,
                   away_price, home_label=None, away_label=None):
    blob = {"timestamp": "2024-09-05T08:25:00Z",
            "previous_timestamp": "2024-09-05T08:25:00Z",
            "next_timestamp": "2024-09-05T08:25:00Z",
            "data": {"id": "e1", "sport_key": "soccer_x",
                     "commence_time": "2024-09-05T19:00:00Z",
                     "home_team": home, "away_team": away,
                     "bookmakers": [
                         {"key": "pinnacle",
                          "last_update": "2024-09-05T08:20:00Z",
                          "markets": [{"key": "h2h",
                                       "last_update": "2024-09-05T08:20:00Z",
                                       "outcomes": [
                                           {"name": home_label or home,
                                            "price": home_price},
                                           {"name": "Draw",
                                            "price": draw_price},
                                           {"name": away_label or away,
                                            "price": away_price}]}]}]}}
    (tmp_path / f"{digest}.json").write_text(json.dumps(blob))


def test_book_prices_map_by_team_name_through_aliases(runner, tmp_path):
    _snapshot_blob(tmp_path, "d1", home="United States", away="Wales",
                   home_price=2.0, draw_price=3.5, away_price=4.0,
                   home_label="USA")
    got = runner.book_prices_from_archive(
        "d1", home="United States", away="Wales",
        aliases={"usa": "United States"}, raw_dir=tmp_path)
    assert got == {"home": 2.0, "draw": 3.5, "away": 4.0}


def test_book_prices_survive_a_home_away_flip(runner, tmp_path):
    # the wire lists the fixture the other way round; mapping is by NAME,
    # so the store's home team keeps the store's home price
    _snapshot_blob(tmp_path, "d2", home="B", away="A", home_price=5.0,
                   draw_price=3.5, away_price=1.7)
    got = runner.book_prices_from_archive("d2", home="A", away="B",
                                          aliases={}, raw_dir=tmp_path)
    assert got == {"home": 1.7, "draw": 3.5, "away": 5.0}


def test_unmappable_outcomes_are_refused(runner, tmp_path):
    _snapshot_blob(tmp_path, "d3", home="X", away="Y", home_price=2.0,
                   draw_price=3.5, away_price=4.0)
    with pytest.raises(runner.DevOofError, match="could not map"):
        runner.book_prices_from_archive("d3", home="A", away="B",
                                        aliases={}, raw_dir=tmp_path)


def test_missing_archive_blob_is_refused(runner, tmp_path):
    with pytest.raises(runner.DevOofError, match="absent from"):
        runner.book_prices_from_archive("nope", home="A", away="B",
                                        aliases={}, raw_dir=tmp_path)


def test_manifest_coverage_drift_is_refused(runner, tmp_path):
    (tmp_path / "m.yaml").write_text(
        "fixtures:\n- match_id: f1\n  date: '2024-09-05'\n"
        "  home_team: A\n  away_team: B\n  tournament: T\n")
    (tmp_path / "c.yaml").write_text("coverage: []\n")
    with pytest.raises(runner.DevOofError, match="drifted"):
        runner.load_inputs(tmp_path / "m.yaml", tmp_path / "c.yaml")
