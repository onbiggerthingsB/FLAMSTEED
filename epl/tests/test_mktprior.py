"""The market-prior harness, held to the preregistration that precedes it.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_mktprior.py -q

`reports/epl_anchoring_prereg.md` (ed40f27) fixes the mechanism, the grid, the
selection, the estimand, the control, the canaries, the refusals and the
adoption rule BEFORE any harness existed. These tests hold `epl.mktprior` to
that document, and they are shaped around the ways this run could produce a
number nobody should believe:

* **A closing price reaching the anchor.** §0.2 measures the close-to-open leak
  at +0.001385 on `Avg`; §5.1 makes reading a `*C*` column a typed refusal.
  Tested on a synthetic file that carries both.
* **A fixture's own odds pricing itself.** §2.3 rules that only matches already
  played may enter `z_mkt`. The existing `point_in_time_canary` rewrites
  RESULTS and is blind to odds, so §5.4's odds canary is the guard, and it has
  a positive leg because a canary that cannot fail is not a canary.
* **A selection that saw the season it prices.** §2.4's LOSO is in-fold by
  construction; `FoldLeak` and `GridEscape` are the refusals, tested with a
  hand-computed fold.
* **A partial run that scores anyway.** 1,060 fits across shards is many ways
  to lose a fit quietly. The merge is tested against a missing shard, a short
  shard, a poisoned shard and an unfrozen harness.
* **Arithmetic nobody checked.** The estimand, the bootstrap and the ridge
  solve are tested against values computed by hand here, not against the
  harness's own output.

CI HAS NO `data/`. Every test that needs a corpus, an archive or a panel builds
its own from synthetic CSV text, and every fit is a deterministic injected stub,
so **nothing here runs an ADVI fit**. The handful of tests that read the pinned
parquet, the archive or the committed prereg are guarded on the file's
existence and skip.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import mktprior as mp

#: Artifacts that exist on the machine that ran the walk and nowhere else.
PINNED_CORPUS = Path("data/epl/fit/walkforward_predictions.parquet")
ARCHIVE_DIR = Path("data/epl/raw")
SNAPSHOT_DIR = Path("data/epl/odds_snapshots")
PREREG = Path("reports/epl_anchoring_prereg.md")


# ==========================================================================
# synthetic source files — the reader's whole world in CI
# ==========================================================================
def _csv(rows: list[dict], columns: list[str]) -> str:
    """A football-data-shaped CSV from explicit columns and rows."""
    out = [",".join(columns)]
    for row in rows:
        out.append(",".join("" if row.get(c) is None else str(row[c])
                            for c in columns))
    return "\n".join(out) + "\n"


_MODERN = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
           "PSH", "PSD", "PSA", "AvgH", "AvgD", "AvgA",
           "PSCH", "PSCD", "PSCA", "AvgCH", "AvgCD", "AvgCA"]
_LEGACY = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
           "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA"]


def _modern_csv() -> str:
    """Two matches with BOTH opening triples and both closing triples.

    The closing prices are deliberately far from the opening ones, so a reader
    that took the close would be caught by the value and not only by the name.
    """
    rows = [
        {"Div": "E0", "Date": "10/08/2019", "HomeTeam": "Liverpool",
         "AwayTeam": "Norwich", "FTHG": 4, "FTAG": 1, "FTR": "H",
         "PSH": 1.30, "PSD": 6.00, "PSA": 11.0,
         "AvgH": 1.28, "AvgD": 6.20, "AvgA": 10.5,
         "PSCH": 9.99, "PSCD": 9.99, "PSCA": 9.99,
         "AvgCH": 8.88, "AvgCD": 8.88, "AvgCA": 8.88},
        {"Div": "E0", "Date": "11/08/2019", "HomeTeam": "Arsenal",
         "AwayTeam": "Everton", "FTHG": 1, "FTAG": 0, "FTR": "H",
         "PSH": 1.90, "PSD": 3.70, "PSA": 4.20,
         "AvgH": 1.95, "AvgD": 3.60, "AvgA": 4.00,
         "PSCH": 9.99, "PSCD": 9.99, "PSCA": 9.99,
         "AvgCH": 8.88, "AvgCD": 8.88, "AvgCA": 8.88},
    ]
    return _csv(rows, _MODERN)


def _legacy_csv() -> str:
    """A pre-2019/20 file: Pinnacle only, no `Avg` column at all."""
    rows = [
        {"Div": "E0", "Date": "16/08/14", "HomeTeam": "Man United",
         "AwayTeam": "Swansea", "FTHG": 1, "FTAG": 2, "FTR": "A",
         "PSH": 1.55, "PSD": 4.30, "PSA": 6.50,
         "PSCH": 9.99, "PSCD": 9.99, "PSCA": 9.99},
        {"Div": "E0", "Date": "16/08/14", "HomeTeam": "Chelsea",
         "AwayTeam": "Burnley", "FTHG": 3, "FTAG": 1, "FTR": "H",
         "PSH": 1.25, "PSD": 6.50, "PSA": 13.0,
         "PSCH": 9.99, "PSCD": 9.99, "PSCA": 9.99},
    ]
    return _csv(rows, _LEGACY)


# ==========================================================================
# 1. the reader — Avg at the open, PS where Avg is not born yet
# ==========================================================================
def test_reader_takes_the_avg_opening_triple_when_it_is_there():
    frame = mp.read_opening_odds(_modern_csv(), label="2019/20")
    assert list(frame["src"]) == ["Avg", "Avg"]
    assert frame.loc[0, "h"] == pytest.approx(1.28)
    assert frame.loc[0, "d"] == pytest.approx(6.20)
    assert frame.loc[0, "a"] == pytest.approx(10.5)
    assert list(frame["home"]) == ["liverpool", "arsenal"]
    assert list(frame["away"]) == ["norwich", "everton"]


def test_reader_falls_back_to_ps_opening_where_avg_is_absent():
    frame = mp.read_opening_odds(_legacy_csv(), label="2014/15")
    assert list(frame["src"]) == ["PS", "PS"]
    assert sorted(frame["h"]) == pytest.approx([1.25, 1.55])


def test_reader_never_returns_a_closing_price():
    """§0.2's timing leak is +0.001385; §3.4 bans scoring against the close."""
    frame = mp.read_opening_odds(_modern_csv(), label="2019/20")
    for col in ("h", "d", "a"):
        assert not (frame[col] == 9.99).any(), "a Pinnacle CLOSING price leaked"
        assert not (frame[col] == 8.88).any(), "an Avg CLOSING price leaked"


def test_the_ruled_columns_carry_no_closing_marker():
    assert mp.AVG_OPENING == ("AvgH", "AvgD", "AvgA")
    assert mp.PS_OPENING == ("PSH", "PSD", "PSA")
    for col in mp.AVG_OPENING + mp.PS_OPENING:
        assert "C" not in col[3:], f"{col} looks like a closing column"


def test_reading_a_closing_column_is_a_typed_refusal():
    with pytest.raises(mp.ClosingOddsRead):
        mp.assert_opening_columns(("AvgCH", "AvgCD", "AvgCA"))
    with pytest.raises(mp.ClosingOddsRead):
        mp.assert_opening_columns(("PSCH", "PSCD", "PSCA"))
    mp.assert_opening_columns(mp.AVG_OPENING)          # does not raise


def test_reader_refuses_a_file_with_no_opening_triple_at_all():
    text = _csv([{"Div": "E0", "Date": "10/08/2019", "HomeTeam": "Liverpool",
                  "AwayTeam": "Norwich", "FTHG": 1, "FTAG": 0, "FTR": "H",
                  "PSCH": 2.0, "PSCD": 3.0, "PSCA": 4.0}],
                ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
                 "PSCH", "PSCD", "PSCA"])
    with pytest.raises(mp.OddsPanelMismatch):
        mp.read_opening_odds(text, label="fabricated")


def test_reader_voids_a_partial_or_degenerate_triple_rather_than_half_using_it():
    """§5.1's `OddsTripleIncomplete`: the panel imputes nothing."""
    rows = [
        {"Div": "E0", "Date": "10/08/2019", "HomeTeam": "Liverpool",
         "AwayTeam": "Norwich", "FTHG": 1, "FTAG": 0, "FTR": "H",
         "PSH": 1.30, "PSD": 6.00, "PSA": 11.0,
         "AvgH": 1.28, "AvgD": None, "AvgA": 10.5},          # partial Avg
        {"Div": "E0", "Date": "11/08/2019", "HomeTeam": "Arsenal",
         "AwayTeam": "Everton", "FTHG": 1, "FTAG": 0, "FTR": "H",
         "PSH": 1.90, "PSD": 3.70, "PSA": 4.20,
         "AvgH": 1.0, "AvgD": 3.60, "AvgA": 4.00},           # price at 1.0
    ]
    cols = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
            "PSH", "PSD", "PSA", "AvgH", "AvgD", "AvgA"]
    frame = mp.read_opening_odds(_csv(rows, cols), label="2019/20")
    # both rows fall back to PS: a triple is used whole or not at all
    assert list(frame["src"]) == ["PS", "PS"]
    assert frame.loc[0, "d"] == pytest.approx(6.00)


def test_a_row_with_no_usable_triple_anywhere_is_absent_not_imputed():
    rows = [{"Div": "E0", "Date": "10/08/2019", "HomeTeam": "Liverpool",
             "AwayTeam": "Norwich", "FTHG": 1, "FTAG": 0, "FTR": "H",
             "PSH": None, "PSD": None, "PSA": None,
             "AvgH": None, "AvgD": None, "AvgA": None},
            {"Div": "E0", "Date": "11/08/2019", "HomeTeam": "Arsenal",
             "AwayTeam": "Everton", "FTHG": 1, "FTAG": 0, "FTR": "H",
             "PSH": 1.90, "PSD": 3.70, "PSA": 4.20,
             "AvgH": 1.95, "AvgD": 3.60, "AvgA": 4.00}]
    cols = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
            "PSH", "PSD", "PSA", "AvgH", "AvgD", "AvgA"]
    frame = mp.read_opening_odds(_csv(rows, cols), label="2019/20")
    assert len(frame) == 1
    assert frame.loc[0, "home"] == "arsenal"


def test_reader_parses_both_source_date_formats():
    modern = mp.read_opening_odds(_modern_csv(), label="2019/20")
    legacy = mp.read_opening_odds(_legacy_csv(), label="2014/15")
    assert list(modern["date"]) == [pd.Timestamp("2019-08-10"),
                                    pd.Timestamp("2019-08-11")]
    assert set(legacy["date"]) == {pd.Timestamp("2014-08-16")}


# ==========================================================================
# 2. the panel — one object, one digest, no imputation
# ==========================================================================
def _panel_from(texts: dict[str, str], max_date="2026-01-01") -> mp.OddsPanel:
    return mp.build_panel(sources=texts, max_date=max_date)


def test_panel_is_sorted_by_date_home_away_and_carries_its_source():
    panel = _panel_from({"1415": _legacy_csv(), "1920": _modern_csv()})
    frame = panel.frame
    assert list(frame["date"]) == sorted(frame["date"])
    assert set(frame["src"]) == {"PS", "Avg"}
    assert panel.n_avg == 2 and panel.n_ps == 2
    assert len(frame) == 4


def test_panel_digest_is_the_prereg_recipe_and_ignores_input_order():
    a = _panel_from({"1415": _legacy_csv(), "1920": _modern_csv()})
    b = _panel_from({"1920": _modern_csv(), "1415": _legacy_csv()})
    assert a.sha256 == b.sha256

    # the recipe, recomputed here rather than read back from the harness
    records = [{"date": str(pd.Timestamp(r.date).date()), "home": r.home,
                "away": r.away, "src": r.src, "h": round(float(r.h), 4),
                "d": round(float(r.d), 4), "a": round(float(r.a), 4)}
               for r in a.frame.itertuples()]
    records.sort(key=lambda x: (x["date"], x["home"], x["away"]))
    want = hashlib.sha256(json.dumps(
        records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert a.sha256 == want


def test_panel_max_date_is_exclusive_and_bounds_what_the_experiment_reads():
    panel = _panel_from({"1920": _modern_csv()}, max_date="2019-08-11")
    assert len(panel.frame) == 1
    assert panel.frame.loc[0, "date"] == pd.Timestamp("2019-08-10")


def test_panel_carries_the_devigged_vector_and_the_market_log_odds():
    panel = _panel_from({"1920": _modern_csv()})
    row = panel.frame.iloc[0]
    inv = np.array([1 / row["h"], 1 / row["d"], 1 / row["a"]])
    want = inv / inv.sum()
    assert row["p_home"] == pytest.approx(want[0], abs=1e-12)
    assert row["p_draw"] == pytest.approx(want[1], abs=1e-12)
    assert row["p_away"] == pytest.approx(want[2], abs=1e-12)
    assert row["m"] == pytest.approx(np.log(want[0] / want[2]), abs=1e-12)


def test_assert_panel_refuses_a_panel_that_is_not_the_pinned_one():
    panel = _panel_from({"1920": _modern_csv()})
    with pytest.raises(mp.OddsPanelMismatch):
        mp.assert_panel(panel)                    # 2 rows, not 4,167


def test_assert_panel_accepts_the_panel_it_is_told_to_expect():
    panel = _panel_from({"1415": _legacy_csv(), "1920": _modern_csv()})
    mp.assert_panel(panel, rows=4, n_avg=2, n_ps=2, sha256=panel.sha256)


def test_source_digest_guard_refuses_a_changed_archive_file(tmp_path):
    good = tmp_path / "E0_1920.csv"
    good.write_text(_modern_csv())
    digest = mp.sha256_file(good)
    mp.assert_source_digests({"1920": good}, {"1920": digest})
    good.write_text(_modern_csv() + "\n")
    with pytest.raises(mp.OddsSourceDigestMismatch):
        mp.assert_source_digests({"1920": good}, {"1920": digest})


def test_the_pinned_source_digests_are_the_eleven_the_document_lists():
    """§0.3's table. The count is read off the list, not off its prose."""
    assert len(mp.ODDS_SOURCE_SHA256) == 11
    assert set(mp.ODDS_SOURCE_SHA256) == {
        "1415", "1516", "1617", "1718", "1819", "1920",
        "2021", "2122", "2223", "2324", "2425"}
    assert all(len(v) == 64 for v in mp.ODDS_SOURCE_SHA256.values())
    assert "2526" not in mp.ODDS_SOURCE_SHA256, (
        "E0_2526's earliest match is after the last cutoff; a file no cutoff "
        "can reach is not part of the panel")


# ==========================================================================
# 3. the same tests against the real archive, where it exists
# ==========================================================================
@pytest.mark.skipif(not ARCHIVE_DIR.exists(), reason="no data/epl/raw")
def test_the_real_archive_reproduces_the_preregistered_panel():
    """§0.3's pin: 4,167 rows, Avg 2,267, PS 1,900, `84ea5621…`."""
    mp.assert_source_digests()
    panel = mp.build_panel()
    assert len(panel.frame) == mp.PANEL_ROWS
    assert panel.n_avg == mp.PANEL_AVG_ROWS
    assert panel.n_ps == mp.PANEL_PS_ROWS
    assert panel.sha256 == mp.PANEL_SHA256
    mp.assert_panel(panel)


@pytest.mark.skipif(not ARCHIVE_DIR.exists(), reason="no data/epl/raw")
def test_avg_is_present_in_every_season_the_live_arm_would_read():
    """§0.3: `Avg` from 2019/20 onward, `PS` only before it."""
    for code in ("1920", "2021", "2122", "2223", "2324", "2425"):
        frame = mp.read_season_opening_odds(code)
        assert set(frame["src"]) == {"Avg"}, f"{code} is not all-Avg"
    for code in ("1415", "1516", "1617", "1718", "1819"):
        frame = mp.read_season_opening_odds(code)
        assert set(frame["src"]) == {"PS"}, f"{code} should be PS-only"


@pytest.mark.skipif(not SNAPSHOT_DIR.exists(), reason="no odds snapshots")
def test_the_live_fixtures_snapshot_carries_the_ruled_column_and_no_pinnacle():
    """§0.3: Pinnacle is absent as a column from the 2026/27 fixtures file."""
    snaps = sorted(SNAPSHOT_DIR.glob("fixtures_*.csv"))
    if not snaps:
        pytest.skip("no captured fixtures file")
    header = snaps[-1].read_text().splitlines()[0].split(",")
    assert all(c in header for c in mp.AVG_OPENING)
    assert not any(c in header for c in mp.PS_OPENING), (
        "Pinnacle has reappeared in the live feed; §0.3's ruling that Avg is "
        "the only column present in every season read is worth re-checking")


# ==========================================================================
# 4. the window — §2.1 Step 1, and the leakage clause §2.3 rules
# ==========================================================================
_CLUBS = ("liverpool", "arsenal", "everton", "chelsea")


def _synthetic_panel(start="2018-01-06", weeks=60, *, strength=None,
                     max_date="2030-01-01") -> mp.OddsPanel:
    """A two-year fixture list over four clubs with a known strength ordering.

    Prices are generated from an explicit `s` and a home edge, so the inversion
    of §2.1 has a right answer the test knows in advance.
    """
    strength = strength or {"liverpool": 0.9, "arsenal": 0.3,
                            "everton": -0.4, "chelsea": -0.8}
    eta = 0.35
    pairs = [(h, a) for h in _CLUBS for a in _CLUBS if h != a]
    rows = []
    day = pd.Timestamp(start)
    for wk in range(weeks):
        h, a = pairs[wk % len(pairs)]
        m = eta + strength[h] - strength[a]
        # a 1X2 book with a fixed draw share and the required home/away ratio
        p_d = 0.25
        p_h = (1 - p_d) * np.exp(m) / (1 + np.exp(m))
        p_a = (1 - p_d) - p_h
        over = 1.05
        rows.append({"Div": "E0",
                     "Date": (day + pd.Timedelta(weeks=wk)).strftime("%d/%m/%Y"),
                     "HomeTeam": _RAW[h], "AwayTeam": _RAW[a],
                     "FTHG": 1, "FTAG": 0, "FTR": "H",
                     "AvgH": round(1.0 / (p_h * over), 4),
                     "AvgD": round(1.0 / (p_d * over), 4),
                     "AvgA": round(1.0 / (p_a * over), 4)})
    cols = ["Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
            "AvgH", "AvgD", "AvgA"]
    return mp.build_panel(sources={"synth": _csv(rows, cols)},
                          max_date=max_date)


_RAW = {"liverpool": "Liverpool", "arsenal": "Arsenal",
        "everton": "Everton", "chelsea": "Chelsea"}


def test_window_takes_nothing_dated_on_or_after_the_cutoff():
    """§2.3, the whole clause: a fixture kicking off at or after C contributes
    nothing to the prior of the fit that prices it."""
    panel = _synthetic_panel()
    cutoff = "2018-06-09"                      # a match falls exactly here
    on_the_day = panel.frame.loc[panel.frame["date"] == pd.Timestamp(cutoff)]
    assert len(on_the_day) == 1, "the fixture set up for this test moved"
    window = mp.market_window(panel, cutoff)
    assert (window["date"] < pd.Timestamp(cutoff)).all()
    assert len(window) > 0


def test_window_takes_nothing_older_than_the_decay_half_life():
    panel = _synthetic_panel()
    cutoff = "2019-01-05"
    window = mp.market_window(panel, cutoff)
    assert (window["date"] >= pd.Timestamp(cutoff)
            - pd.Timedelta(days=mp.MARKET_WINDOW_DAYS)).all()


def test_window_keeps_a_row_only_if_it_is_recent_for_one_of_its_clubs():
    """§2.1 Step 1: the M most recent of EITHER club, M = 10, not tuned."""
    panel = _synthetic_panel(weeks=120)
    cutoff = "2020-04-20"
    window = mp.market_window(panel, cutoff)
    frame = panel.frame
    prior = frame.loc[frame["date"] < pd.Timestamp(cutoff)]
    for club in _CLUBS:
        mine = prior.loc[(prior["home"] == club) | (prior["away"] == club)]
        kept = window.loc[(window["home"] == club) | (window["away"] == club)]
        newest = set(mine.sort_values("date")["date"].tail(
            mp.MARKET_WINDOW_MATCHES))
        # every row this club contributed is among its M most recent
        assert set(kept["date"]) <= set(mine["date"])
        assert newest <= set(window["date"]) | set()
    assert mp.MARKET_WINDOW_MATCHES == 10
    assert mp.MARKET_WINDOW_DAYS == 365


def test_a_leaked_window_is_a_typed_refusal():
    panel = _synthetic_panel()
    frame = panel.frame
    leaked = frame.loc[frame["date"] >= pd.Timestamp("2018-06-09")].head(3)
    with pytest.raises(mp.OddsLeak):
        mp.assert_no_odds_leak(leaked, "2018-06-09")


def test_the_windows_own_rows_are_never_the_fixtures_being_priced():
    panel = _synthetic_panel()
    cutoff = "2018-06-09"
    window = mp.market_window(panel, cutoff)
    priced = panel.frame.loc[panel.frame["date"] >= pd.Timestamp(cutoff)]
    pairs_priced = {(r.date, r.home, r.away) for r in priced.itertuples()}
    pairs_window = {(r.date, r.home, r.away) for r in window.itertuples()}
    assert not (pairs_priced & pairs_window)


# ==========================================================================
# 5. the inversion — §2.1 Step 3, checked against arithmetic done by hand
# ==========================================================================
def _window(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": pd.Timestamp(d), "home": h, "away": a, "src": "Avg",
          "h": 2.0, "d": 3.0, "a": 4.0, "m": m}
         for d, h, a, m in rows])


def test_the_ridge_never_penalises_the_home_advantage():
    """One match, one degree of freedom: `eta` absorbs it and `s` shrinks to 0.

    This is the direct test of §2.1 Step 3's "ridge penalty lambda = 1.0 on the
    club coefficients `s` only, never on `eta`". A penalised `eta` would split
    the signal between them and neither number below would hold.
    """
    win = _window([("2020-01-01", "liverpool", "arsenal", 0.5)])
    rec = mp.recover_strength(win, "2020-01-02", check=False)
    assert rec.eta == pytest.approx(0.5, abs=1e-12)
    assert rec.strength["liverpool"] == pytest.approx(0.0, abs=1e-12)
    assert rec.strength["arsenal"] == pytest.approx(0.0, abs=1e-12)


def test_the_solve_reproduces_a_two_match_answer_computed_by_hand():
    """Two mirrored matches at one date. With a common decay weight `w0`:

        eta = 0.5 exactly, independent of the decay
        s[liverpool] = w0 / (4 w0 + 1),  s[arsenal] = -s[liverpool]
    """
    win = _window([("2020-01-01", "liverpool", "arsenal", 1.0),
                   ("2020-01-01", "arsenal", "liverpool", 0.0)])
    cutoff = "2020-01-11"
    rec = mp.recover_strength(win, cutoff, check=False)
    w0 = 0.5 ** (10.0 / mp.DECAY_HALF_LIFE_DAYS)
    assert rec.eta == pytest.approx(0.5, abs=1e-12)
    assert rec.strength["liverpool"] == pytest.approx(w0 / (4 * w0 + 1),
                                                      abs=1e-12)
    assert rec.strength["arsenal"] == pytest.approx(-w0 / (4 * w0 + 1),
                                                    abs=1e-12)


def test_the_solve_weighs_a_recent_match_above_an_old_one():
    """Two same-orientation matches collapse `s` to zero and leave `eta` as the
    DECAY-WEIGHTED mean of their `m`, which is a closed form the test can check.

    An unweighted fit would return 0.5. The pipeline's own weight,
    `0.5 ** (age_days / 365)` (`src/wcmodel/data/features.py:297`), returns
    `w_recent / (w_recent + w_old)` — and the point of reusing that weight
    rather than choosing one is that the market anchor's memory is then the
    likelihood's memory and not a second free knob (§2.1 Step 3).
    """
    win = _window([("2020-01-01", "liverpool", "arsenal", 1.0),
                   ("2019-03-07", "liverpool", "arsenal", 0.0)])
    rec = mp.recover_strength(win, "2020-01-02", check=False)
    w_recent = 0.5 ** (1.0 / mp.DECAY_HALF_LIFE_DAYS)
    w_old = 0.5 ** (301.0 / mp.DECAY_HALF_LIFE_DAYS)
    assert rec.eta == pytest.approx(w_recent / (w_recent + w_old), abs=1e-12)
    assert rec.eta > 0.5, "an unweighted fit would return exactly 0.5"


def test_the_solve_recovers_a_planted_strength_ordering():
    panel = _synthetic_panel(weeks=120)
    rec = mp.recover_strength(mp.market_window(panel, "2020-04-20"),
                              "2020-04-20")
    order = sorted(rec.strength, key=rec.strength.get, reverse=True)
    assert order == ["liverpool", "arsenal", "everton", "chelsea"]
    assert mp.ETA_BAND[0] < rec.eta < mp.ETA_BAND[1]


def test_an_eta_outside_the_pre_stated_band_is_a_typed_refusal():
    win = _window([("2020-01-01", "liverpool", "arsenal", 4.0)])
    with pytest.raises(mp.RecoveryUnstable):
        mp.recover_strength(win, "2020-01-02")


def test_an_empty_window_recovers_nothing_rather_than_guessing():
    rec = mp.recover_strength(_window([]), "2020-01-02", check=False)
    assert rec.strength == {}
    assert rec.n_matches == 0


# ==========================================================================
# 6. z_mkt — §2.1 Step 4, `team_elo_z`'s contract, clause for clause
# ==========================================================================
def test_z_mkt_mirrors_team_elo_z_for_a_club_with_no_window_match():
    """§2.1: "A fitted club with no window match gets z_mkt = 0."

    `wcmodel.model.strength.team_elo_z` computes mean and sd over the teams it
    HAS and then sets an absent team to exactly 0 — not to `(0 - mean)/sd`.
    This is that contract, and it is why the absent club sits at the present
    clubs' mean rather than somewhere below it.
    """
    panel = _synthetic_panel(weeks=120)
    fitted = list(_CLUBS) + ["norwich"]
    z = mp.market_z(panel, "2020-04-20", fitted)
    assert z[-1] == 0.0
    present = z[:-1]
    assert float(np.mean(present)) == pytest.approx(0.0, abs=1e-12)
    assert float(np.std(present)) == pytest.approx(1.0, abs=1e-12)


def test_z_mkt_is_all_zeros_when_the_clubs_do_not_differ():
    win = _window([("2020-01-01", "liverpool", "arsenal", 1.0),
                   ("2020-01-01", "arsenal", "liverpool", 1.0)])
    rec = mp.recover_strength(win, "2020-01-02", check=False)
    z = mp.z_from_strength(rec, ["liverpool", "arsenal"])
    assert list(z) == [0.0, 0.0]


def test_a_degenerate_strength_vector_is_refused_where_it_would_matter():
    win = _window([("2020-01-01", "liverpool", "arsenal", 1.0),
                   ("2020-01-01", "arsenal", "liverpool", 1.0)])
    rec = mp.recover_strength(win, "2020-01-02", check=False)
    with pytest.raises(mp.DegenerateStrength):
        mp.assert_strength_disperses(rec)


def test_z_mkt_is_ordered_the_way_the_planted_strengths_are():
    panel = _synthetic_panel(weeks=120)
    z = mp.market_z(panel, "2020-04-20", list(_CLUBS))
    assert list(np.argsort(-z)) == [0, 1, 2, 3]


# ==========================================================================
# 7. the blend — §2.2's ruling: rotation, not addition
# ==========================================================================
def test_w_zero_is_the_elo_anchor_exactly_and_not_to_round_off():
    """§2.2: "z_blend(0) := elo_z EXACTLY", which is what makes §3.2's control
    a check on archive drift instead of a check on arithmetic."""
    ez = np.array([1.7, -0.3, -0.4, -1.0])
    zm = np.array([0.9, 0.3, -0.4, -0.8])
    out = mp.blend(ez, zm, 0.0)
    assert np.array_equal(out, ez)
    assert out.tobytes() == ez.tobytes()


def test_w_one_is_the_market_direction_z_scored_over_the_fitted_teams():
    ez = np.array([1.7, -0.3, -0.4, -1.0])
    zm = np.array([2.0, 1.0, 0.0, -3.0])
    out = mp.blend(ez, zm, 1.0)
    want = (zm - zm.mean()) / zm.std()
    assert out == pytest.approx(want, abs=1e-12)


def test_an_intermediate_weight_is_the_z_score_of_the_mixture():
    ez = np.array([1.7, -0.3, -0.4, -1.0])
    zm = np.array([0.9, 0.3, -0.4, -0.8])
    for w in (0.15, 0.30, 0.50, 0.75):
        mix = (1 - w) * ez + w * zm
        want = (mix - mix.mean()) / mix.std()
        got = mp.blend(ez, zm, w)
        assert got == pytest.approx(want, abs=1e-12)
        assert float(np.mean(got)) == pytest.approx(0.0, abs=1e-12)
        assert float(np.std(got)) == pytest.approx(1.0, abs=1e-12)


def test_the_blend_never_changes_how_hard_the_prior_pulls():
    """§2.2 (ii): the market term travels inside the SAME vector at the SAME
    `k`, so the net multiplier on the strength difference is 2 x 0.6 = 1.2 at
    every `w`, identical to today's. A unit-sd vector at every `w` is what
    makes that true, and it is what an ADDITIVE term would have broken.

    `elo_z` arrives unit-sd because it is already a z-score over the fitted
    teams (`epl.anchor.AnchorState.elo_z`), so `w = 0` belongs in this loop.
    """
    raw = np.array([1.7, -0.3, -0.4, -1.0])
    ez = (raw - raw.mean()) / raw.std()
    zm = np.array([0.9, 0.3, -0.4, -0.8])
    zm = (zm - zm.mean()) / zm.std()
    for w in mp.W_GRID:
        got = mp.blend(ez, zm, w)
        assert float(np.std(got)) == pytest.approx(1.0, abs=1e-12)


def test_a_weight_off_the_frozen_grid_is_a_typed_refusal():
    ez = np.array([1.0, -1.0])
    zm = np.array([1.0, -1.0])
    for bad in (0.2, -0.1, 1.5):
        with pytest.raises(mp.GridEscape):
            mp.blend(ez, zm, bad)


def test_the_grid_is_the_six_points_the_document_fixed():
    assert mp.W_GRID == (0.00, 0.15, 0.30, 0.50, 0.75, 1.00)
    assert mp.W_GRID[0] == 0.0, "the selection must be allowed to say no"
    assert len(mp.W_GRID) == 6


# ==========================================================================
# 8. the odds canary — §5.4, and it has a positive leg on purpose
# ==========================================================================
def test_the_odds_canary_passes_when_the_window_respects_the_cutoff():
    panel = _synthetic_panel(weeks=200)
    out = mp.run_odds_canary(panel, "2020-04-20", list(_CLUBS), write=False)
    assert out["PASS"] is True
    assert out["max_abs_diff_after_cutoff"] == 0.0
    assert out["max_abs_diff_positive_control"] > 1e-9


def test_the_odds_canary_fails_a_z_function_that_reads_the_future():
    """A canary that cannot fail is not a canary (§5.4)."""
    panel = _synthetic_panel(weeks=200)

    def leaky(pan, cutoff, teams):
        rec = mp.recover_strength(pan.frame, cutoff, check=False)
        return mp.z_from_strength(rec, teams)

    with pytest.raises(mp.MarketCanaryFailed):
        mp.run_odds_canary(panel, "2020-04-20", list(_CLUBS), z_fn=leaky,
                           write=False)


def test_the_odds_canary_fails_a_z_function_that_ignores_the_odds():
    """The positive leg: corrupt the PAST and the anchor must move."""
    panel = _synthetic_panel(weeks=200)

    def blind(pan, cutoff, teams):
        return np.zeros(len(teams), dtype=float)

    with pytest.raises(mp.MarketCanaryFailed):
        mp.run_odds_canary(panel, "2020-04-20", list(_CLUBS), z_fn=blind,
                           write=False)


def test_the_odds_canary_corrupts_prices_that_are_still_a_real_book():
    """The perturbation has to move the de-vigged vector materially and still
    leave prices a de-vig will accept, or the canary tests the de-vig's input
    validation instead of the leakage rule.

    Exchanging home and away preserves the inverse-price sum exactly, so the
    corrupted panel is still a book with the same overround — a multiplier on
    one price is not, and `devig.proportional` refuses it.
    """
    panel = _synthetic_panel(weeks=200)
    corrupted = mp.corrupt_odds(panel, on_or_after="2020-04-20")
    assert (corrupted.frame[["h", "d", "a"]].to_numpy() > 1.0).all()
    over_before = (1.0 / panel.frame[["h", "d", "a"]].to_numpy()).sum(axis=1)
    over_after = (1.0 / corrupted.frame[["h", "d", "a"]].to_numpy()).sum(axis=1)
    assert over_after == pytest.approx(over_before, abs=1e-12)
    moved = corrupted.frame["m"].to_numpy() - panel.frame["m"].to_numpy()
    after = (panel.frame["date"] >= pd.Timestamp("2020-04-20")).to_numpy()
    assert after.sum() > 0 and (~after).sum() > 0
    assert np.abs(moved[after]).min() > 1e-3
    assert np.abs(moved[~after]).max() == 0.0


def test_a_canary_leg_with_nothing_to_corrupt_is_a_refusal_not_a_pass():
    """A negative leg that could not have caught anything passes for the wrong
    reason, which is worse than failing (§5.4)."""
    panel = _synthetic_panel(weeks=120)          # every row precedes the cutoff
    with pytest.raises(mp.MarketCanaryFailed) as exc:
        mp.run_odds_canary(panel, "2024-01-01", list(_CLUBS), write=False)
    assert "nothing to corrupt" in str(exc.value)


def test_require_odds_canary_refuses_an_absent_or_failing_record(tmp_path):
    with pytest.raises(mp.MarketCanaryFailed):
        mp.require_odds_canary(tmp_path / "odds_canary.json")
    path = tmp_path / "odds_canary.json"
    path.write_text(json.dumps({"PASS": False,
                                "max_abs_diff_after_cutoff": 0.4}))
    with pytest.raises(mp.MarketCanaryFailed):
        mp.require_odds_canary(path)
    path.write_text(json.dumps({"PASS": True,
                                "max_abs_diff_after_cutoff": 0.0,
                                "max_abs_diff_positive_control": 0.3}))
    assert mp.require_odds_canary(path)["PASS"] is True


# --------------------------------------------------------------------------
# §2.1's published sanity statistics, recomputed
# --------------------------------------------------------------------------
@pytest.mark.skipif(not ARCHIVE_DIR.exists() or not mp.CORPUS_PATH.exists(),
                    reason="no data/epl/raw or no pinned corpus")
def test_the_documents_published_sanity_statistics_are_stale():
    """§2.1 states its window twice and the two statements disagree.

    THE RED THIS REPLACES, run against the published trio::

        assert (min(n), int(np.median(n)), max(n)) == (201, 233, 262)
        E       assert (101, 129, 138) == (201, 233, 262)

    The definition — "the 10 most recent such matches of *either* club",
    "`M = 10` matches per club", "one club-quarter of a 38-match season" — is
    venue-blind. The published statistics are not: they come from each club's
    10 most recent HOME matches AND 10 most recent AWAY matches, twenty per
    club, with the sd then taken over the season's twenty rather than over
    every club in the window. This test pins BOTH halves, so the amendment
    §2.1 needs has a recorded quantity to correct itself against and cannot be
    settled by a fresh script nobody kept.
    """
    panel = mp.build_panel()
    corpus = pd.read_parquet(mp.CORPUS_PATH)
    corpus["date"] = pd.to_datetime(corpus["date"])
    openings = corpus.groupby("block")["date"].min().sort_values()

    def trio(values):
        return (min(values), float(np.median(values)), max(values))

    # (a) the ruled definition, which is what the harness computes
    ruled = [mp.market_window(panel, c) for c in openings]
    recs = [mp.recover_strength(w, c, check=False)
            for w, c in zip(ruled, openings)]
    assert tuple(int(v) for v in trio([len(w) for w in ruled])) \
        == mp.MEASURED_WINDOW
    assert trio([r.eta for r in recs]) \
        == pytest.approx(mp.MEASURED_ETA, abs=5e-5)
    assert trio([r.sd for r in recs]) \
        == pytest.approx(mp.MEASURED_SD, abs=5e-5)

    # (b) the per-venue variant, which is what produced the published trio
    frame = panel.frame
    dates = frame["date"].to_numpy()
    venue_n, venue_eta, venue_sd = [], [], []
    for c in openings:
        ts = pd.Timestamp(c).normalize()
        lo = (ts - pd.Timedelta(days=mp.MARKET_WINDOW_DAYS)).to_datetime64()
        sel = np.flatnonzero((dates < ts.to_datetime64()) & (dates >= lo))
        home, away = frame["home"].to_numpy()[sel], frame["away"].to_numpy()[sel]
        when = dates[sel]
        keep = np.zeros(sel.size, dtype=bool)
        for club in sorted(set(home) | set(away)):
            for side in (home == club, away == club):
                idx = np.flatnonzero(side)
                order = idx[np.argsort(when[idx], kind="mergesort")][::-1]
                keep[order[:mp.MARKET_WINDOW_MATCHES]] = True
        rec = mp.recover_strength(frame.iloc[sel[keep]].copy(), c, check=False)
        season = corpus.loc[corpus["date"] >= ts, "season"]
        season = season.iloc[0] if len(season) else corpus["season"].iloc[-1]
        rows = corpus.loc[corpus["season"] == season]
        twenty = sorted(set(rows["home_key"]) | set(rows["away_key"]))
        venue_n.append(int(keep.sum()))
        venue_eta.append(rec.eta)
        venue_sd.append(float(np.std([rec.strength[t] for t in twenty
                                      if t in rec.strength])))
    assert tuple(int(v) for v in trio(venue_n)) == mp.DOCUMENTED_WINDOW
    assert trio(venue_eta) == pytest.approx(mp.DOCUMENTED_ETA, abs=5e-5)
    assert trio(venue_sd) == pytest.approx(mp.DOCUMENTED_SD, abs=5e-5)


@pytest.mark.skipif(not ARCHIVE_DIR.exists() or not mp.CORPUS_PATH.exists(),
                    reason="no data/epl/raw or no pinned corpus")
def test_the_one_rule_invariant_claim_of_2_1_does_reproduce():
    """A club absent from the window is absent under either reading.

    §2.1's "7 of 212 cutoffs, 19 of 2,280 fixtures, every one a promoted club's
    opening weekend" does not depend on how many of a present club's matches
    are kept, so it survives the stale annotations — and it is the claim the
    denominator depends on, since §2.6 fixes 2,280 and these nineteen stay in
    it with the market term inert.
    """
    panel = mp.build_panel()
    corpus = pd.read_parquet(mp.CORPUS_PATH)
    corpus["date"] = pd.to_datetime(corpus["date"])
    cutoffs, fixtures = 0, 0
    for block, opening in corpus.groupby("block")["date"].min().items():
        rec = mp.recover_strength(mp.market_window(panel, opening), opening,
                                  check=False)
        rows = corpus.loc[corpus["block"] == block]
        absent = {t for t in set(rows["home_key"]) | set(rows["away_key"])
                  if t not in rec.strength}
        if absent:
            cutoffs += 1
            fixtures += int(rows["home_key"].isin(absent).sum()
                            + rows["away_key"].isin(absent).sum())
    assert cutoffs == mp.MEASURED_ZERO_WINDOW_CUTOFFS
    assert fixtures == mp.MEASURED_ZERO_WINDOW_FIXTURES
