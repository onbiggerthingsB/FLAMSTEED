from pathlib import Path

import pandas as pd

from wcmodel.eval.regulation import load_regulation_table, regulation_outcome


def test_real_table_loads_and_is_complete():
    df = load_regulation_table()
    assert set(df["pool"].unique()) == {"wc2022", "euro2024", "wc2026"}
    counts = df["pool"].value_counts().to_dict()
    assert counts == {"wc2026": 32, "wc2022": 16, "euro2024": 15}
    # every went_et row must be a 90' draw — that's what extra time MEANS
    et = df[df["went_et"]]
    assert (et["h90"] == et["a90"]).all()
    assert df["source"].str.startswith("http").all()


def test_outcome_mapping():
    assert regulation_outcome(2, 1) == "home"
    assert regulation_outcome(0, 0) == "draw"
    assert regulation_outcome(0, 3) == "away"


def test_non_et_rows_match_store_final_scores():
    """Consistency canary: if went_et is False, the 90' score must equal the
    stored final score for that fixture (they are the same event).

    Store choice matters (plan amendment 2026-07-29): data/clv_store/ is a
    STALE mid-tournament snapshot (wc2026 scores all NaN, nothing past
    Jun 27); data/stores/martj42_36675ba is the pinned pre-KO store (only 7
    scored KO rows). The complete store is data/stores/full_final — the one
    scripts/live_scorecard_final.py scored all 104 games from."""
    from wcmodel.data.store import BitemporalStore
    df = load_regulation_table()
    store = BitemporalStore(root=Path("data/stores/full_final")).read(
        "results", cutoff="2026-07-28T00:00:00Z")
    store["date"] = pd.to_datetime(store["date"]).dt.date.astype(str)
    merged = df[~df["went_et"]].merge(
        store, left_on=["date", "home", "away"],
        right_on=["date", "home_team", "away_team"], how="left")
    assert merged["home_score"].notna().all(), \
        f"unmatched fixtures:\n{merged[merged['home_score'].isna()][['date','home','away']]}"
    assert (merged["h90"] == merged["home_score"]).all()
    assert (merged["a90"] == merged["away_score"]).all()
