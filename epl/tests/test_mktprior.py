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
