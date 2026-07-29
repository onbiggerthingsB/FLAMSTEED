"""The curated 90-minute knockout table (OA finding 3).

Three layers: always-on structural/validation tests (no local data needed), the
canonical-mapper pin, and the store cross-check (skipped where the gitignored
store is absent — and self-tested for non-vacuity, since a skip must never be
the reason a curation error goes unseen)."""
from pathlib import Path

import pandas as pd
import pytest
import yaml

from wcmodel.eval.regulation import load_regulation_table, regulation_outcome

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STORE = _REPO_ROOT / "data" / "stores" / "full_final"
# `/data/` is gitignored (.gitignore:16), so a fresh clone or a worktree has no
# store and the cross-check below cannot run there: SKIP with a reason instead
# of erroring out of pandas with a raw FileNotFoundError. Everything that does
# NOT need the store is enforced by the loader and asserted always-on above, so
# the skip narrows the verification to the ground-truth join — it never leaves
# the table wholly unchecked.
_needs_store = pytest.mark.skipif(
    not _STORE.exists(),
    reason=f"{_STORE} absent (gitignored local artifact) — rebuild it to re-arm "
           "the 90'-vs-store cross-check")

_ROW = {"pool": "wc2022", "date": "2022-12-03", "home": "Argentina",
        "away": "Australia", "score_90": [2, 1], "went_et": False,
        "source": "https://example.invalid/match-report"}


def _table(tmp_path, *rows) -> Path:
    path = tmp_path / "table.yaml"
    path.write_text(yaml.safe_dump([dict(r) for r in rows]))
    return path


def test_real_table_loads_and_is_complete():
    df = load_regulation_table()
    assert set(df["pool"].unique()) == {"wc2022", "euro2024", "wc2026"}
    counts = df["pool"].value_counts().to_dict()
    assert counts == {"wc2026": 32, "wc2022": 16, "euro2024": 15}
    # every went_et row must be a 90' draw — that's what extra time MEANS
    et = df[df["went_et"]]
    assert (et["h90"] == et["a90"]).all()
    # ET-count pin. An ET-DECIDED fixture mis-recorded as went_et false carries
    # its ET-inclusive score, which is NOT level, so both loader invariants read
    # it as consistent and the join key is unchanged; for those 7 rows the
    # store's final IS that score, so the non-ET equality check CONFIRMS the
    # corruption while the 1X2 label silently flips. (The other 12 ET rows went
    # to penalties: their stored final is a draw, which does trip the loader.)
    # martj42 keeps only ET-inclusive finals, so no store-derived guard is
    # possible here — the count is the defence.
    assert et["pool"].value_counts().to_dict() == {
        "wc2026": 9, "wc2022": 5, "euro2024": 5}
    assert df["source"].str.startswith("http").all()


def test_real_table_loads_from_any_working_directory(tmp_path, monkeypatch):
    """The consumers are a script and a WSGI app — neither one owns the cwd."""
    monkeypatch.chdir(tmp_path)
    assert len(load_regulation_table()) == 63


def test_normalizes_string_dates_to_iso(tmp_path):
    """An UNQUOTED YAML date parses to datetime.date and normalizes for free;
    a quoted one ("2022-12-3") stays a str that astype(str) leaves un-padded,
    and the only layer that would notice is the store join — which is skipped
    wherever the gitignored store is absent."""
    df = load_regulation_table(_table(tmp_path, {**_ROW, "date": "2022-12-3"}))
    assert df["date"].tolist() == ["2022-12-03"]


def test_rejects_score_90_that_is_not_exactly_two_values(tmp_path):
    for bad in ([2, 1, 0], [2]):
        with pytest.raises(ValueError, match="score_90"):
            load_regulation_table(_table(tmp_path, {**_ROW, "score_90": bad}))


def test_rejects_non_integer_score(tmp_path):
    # int(2.9) == 2 would silently turn a typo into a plausible scoreline.
    with pytest.raises(ValueError, match="integer"):
        load_regulation_table(_table(tmp_path, {**_ROW, "score_90": [2.9, 1]}))


def test_rejects_negative_score(tmp_path):
    with pytest.raises(ValueError, match="negative"):
        load_regulation_table(_table(tmp_path, {**_ROW, "score_90": [-1, 1]}))


def test_rejects_duplicate_fixture(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_regulation_table(_table(tmp_path, _ROW, _ROW))


def test_rejects_row_missing_went_et(tmp_path):
    row = {k: v for k, v in _ROW.items() if k != "went_et"}
    # A one-row table drops the whole COLUMN, which the _REQUIRED check catches;
    # alongside a complete row the column survives as object-dtype NaN, a
    # different code path with the same refusal. Both are real hand-edit shapes.
    with pytest.raises(ValueError, match="went_et"):
        load_regulation_table(_table(tmp_path, row))
    kept = {**_ROW, "date": "2022-12-04", "home": "England", "away": "Senegal",
            "score_90": [3, 0]}
    with pytest.raises(ValueError, match="went_et must be true/false"):
        load_regulation_table(_table(tmp_path, kept, row))


def test_rejects_et_row_that_was_not_level_at_90(tmp_path):
    """The invariants must live in the LOADER, not only in this file: a future
    consumer of a hand-edited YAML never runs the tests."""
    with pytest.raises(ValueError, match="went_et"):
        load_regulation_table(
            _table(tmp_path, {**_ROW, "score_90": [2, 1], "went_et": True}))


def test_rejects_90_draw_not_marked_went_et(tmp_path):
    # Every row is a KNOCKOUT fixture, so a level 90' MUST have gone to ET.
    with pytest.raises(ValueError, match="went_et"):
        load_regulation_table(
            _table(tmp_path, {**_ROW, "score_90": [1, 1], "went_et": False}))


def test_outcome_mapping():
    assert regulation_outcome(2, 1) == "home"
    assert regulation_outcome(0, 0) == "draw"
    assert regulation_outcome(0, 3) == "away"


def test_regulation_outcome_is_the_canonical_mapper():
    # Finding-16 class: ONE score->1X2 implementation, not a fourth copy.
    from wcmodel.model.calibration import outcome_1x2
    for h in range(6):
        for a in range(6):
            assert regulation_outcome(h, a) == outcome_1x2(h, a)


def _merge_store(df: pd.DataFrame) -> pd.DataFrame:
    from wcmodel.data.store import BitemporalStore
    store = BitemporalStore(root=_STORE).read(
        "results", cutoff="2026-07-28T00:00:00Z")
    store["date"] = pd.to_datetime(store["date"]).dt.date.astype(str)
    return df.merge(store, left_on=["date", "home", "away"],
                    right_on=["date", "home_team", "away_team"], how="left")


@_needs_store
def test_every_row_joins_the_store_and_non_et_scores_match():
    """Consistency canary: EVERY row must join the store on (date, home, away),
    and if went_et is False the 90' score must equal the stored final score
    (they are the same event). ET rows are join-checked but NOT score-checked —
    the store's final score for them includes the extra-time goals.

    The join half is the one that guards spelling/date/orientation: a typo in an
    ET row passes every other test here, then silently drops that fixture from
    the Plan-2 scored set (or yields a NaN outcome on a left join).

    Store choice matters (plan amendment 2026-07-29): data/clv_store/ is a
    STALE mid-tournament snapshot (wc2026 scores all NaN, nothing past
    Jun 27); data/stores/martj42_36675ba is the pinned pre-KO store (only 7
    scored KO rows). The complete store is data/stores/full_final — the one
    scripts/live_scorecard_final.py scored all 104 games from."""
    merged = _merge_store(load_regulation_table())
    assert merged["home_score"].notna().all(), \
        f"unmatched fixtures:\n{merged[merged['home_score'].isna()][['date','home','away']]}"
    reg = merged[~merged["went_et"]]
    assert (reg["h90"] == reg["home_score"]).all()
    assert (reg["a90"] == reg["away_score"]).all()


@_needs_store
def test_the_join_check_would_catch_a_misspelled_et_row():
    """Non-vacuity proof for the assertion above: ET rows are guarded ONLY by
    their (date, home, away) key, so prove that key is really checked."""
    df = load_regulation_table()
    i = df.index[df["went_et"]][0]
    df.loc[i, "home"] = df.loc[i, "home"] + " FC"
    assert _merge_store(df)["home_score"].isna().sum() == 1
