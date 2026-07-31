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


def test_rejects_row_with_a_null_identity_field(tmp_path):
    """Same hand-edit shape as the two-row case above, aimed at the identity
    and provenance keys: dropping ONE of them from ONE row leaves the COLUMN
    in place, so the _REQUIRED presence check sees nothing and the row loads
    carrying a NaN. That row then matches nothing on (date, home, away) and
    drops silently out of the Plan-2 scored set — no error, no signal. The
    store cross-check would catch it, but that check is skipped wherever the
    gitignored store is absent, so the guard has to live in the loader."""
    kept = {**_ROW, "date": "2022-12-04", "home": "England", "away": "Senegal",
            "score_90": [3, 0]}
    for field in ("pool", "date", "home", "away", "source"):
        row = {k: v for k, v in _ROW.items() if k != field}
        with pytest.raises(ValueError, match="null"):
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


def _read_store() -> pd.DataFrame:
    from wcmodel.data.store import BitemporalStore
    store = BitemporalStore(root=_STORE).read(
        "results", cutoff="2026-07-28T00:00:00Z")
    store["date"] = pd.to_datetime(store["date"]).dt.date.astype(str)
    return store


def _merge_store(df: pd.DataFrame, store: pd.DataFrame | None = None) -> pd.DataFrame:
    # `store` is injectable so the fan-out proof below can merge against a
    # deliberately duplicated store without touching the real one on disk.
    if store is None:
        store = _read_store()
    return df.merge(store, left_on=["date", "home", "away"],
                    right_on=["date", "home_team", "away_team"], how="left")


@_needs_store
def test_every_row_joins_the_store_and_non_et_scores_match():
    """Consistency canary: EVERY row must join the store on (date, home, away)
    exactly once, and if went_et is False the 90' score must equal the stored
    final score (they are the same event).

    The 19 ET rows get NO equality check — the store's final for them includes
    the extra-time goals — so they rest on the join, the ET-count pin in
    test_real_table_loads_and_is_complete, and the one-way bound below: ET
    goals can only ADD, so no row's 90' score may EXCEED the stored final.
    That leaves ONE hole open, and martj42 cannot close it (it keeps only
    ET-inclusive finals): an UNDERSTATED but still level 90' score on an ET row
    — 1-1 recorded where the truth was 2-2 — satisfies every layer here. The
    overstated direction (2-2 for a true 1-1) is what the bound catches.

    The join half is the one that guards spelling/date/orientation: a typo in an
    ET row passes every other test here, then silently drops that fixture from
    the Plan-2 scored set (or yields a NaN outcome on a left join).

    Store choice matters (plan amendment 2026-07-29): data/clv_store/ is a
    STALE mid-tournament snapshot (wc2026 scores all NaN, nothing past
    Jun 27); data/stores/martj42_36675ba is the pinned pre-KO store (only 7
    scored KO rows). The complete store is data/stores/full_final — the one
    scripts/live_scorecard_final.py scored all 104 games from."""
    df = load_regulation_table()
    merged = _merge_store(df)
    # A LEFT merge FANS OUT silently on a duplicated store key, and nothing
    # else here would notice: the duplicate's scores simply get checked twice.
    # The store HAS carried a duplicate (date, home_team, away_team) pair
    # (1974-02-17 Tahiti v New Caledonia) — the reason valid_played_results
    # dedups — so a duplicated KO row after a re-ingest is a demonstrated
    # shape, not a hypothetical, and the 19 ET rows carry no score check at all.
    assert len(merged) == len(df), f"store fan-out: {len(merged)} rows for {len(df)} fixtures"
    assert merged["home_score"].notna().all(), \
        f"unmatched fixtures:\n{merged[merged['home_score'].isna()][['date','home','away']]}"
    reg = merged[~merged["went_et"]]
    assert (reg["h90"] == reg["home_score"]).all()
    assert (reg["a90"] == reg["away_score"]).all()
    # Extra-time goals only ADD, so 90' <= final holds for EVERY row, ET
    # included — the only store-derived score guard the ET rows admit.
    over = merged[(merged["h90"] > merged["home_score"])
                  | (merged["a90"] > merged["away_score"])]
    assert over.empty, ("90' score exceeds the stored final:\n"
                        f"{over[['date','home','away','h90','a90','home_score','away_score']]}")


@_needs_store
def test_the_join_check_would_catch_a_misspelled_et_row():
    """Non-vacuity proof for the assertion above: ET rows are guarded ONLY by
    their (date, home, away) key, so prove that key is really checked."""
    df = load_regulation_table()
    i = df.index[df["went_et"]][0]
    df.loc[i, "home"] = df.loc[i, "home"] + " FC"
    assert _merge_store(df)["home_score"].isna().sum() == 1


@_needs_store
def test_the_row_count_check_would_catch_a_duplicated_store_row():
    """Non-vacuity proof for `len(merged) == len(df)`. Duplicating a store row
    fans the LEFT merge out, and every other assertion in that test survives it
    untouched — the duplicate carries the same scores, so the equality check
    just confirms them twice. Aimed at an ET row, which has no score check at
    all: the row count is the only thing standing between a re-ingested
    duplicate and a fixture silently counted twice in the Plan-2 scored set."""
    df = load_regulation_table()
    store = _read_store()
    row = df[df["went_et"]].iloc[0]
    hit = ((store["date"] == row["date"]) & (store["home_team"] == row["home"])
           & (store["away_team"] == row["away"]))
    assert hit.sum() == 1, "fixture must be unique in the store to prove the fan-out"
    fanned = pd.concat([store, store[hit]], ignore_index=True)
    assert len(_merge_store(df, fanned)) == len(df) + 1


@_needs_store
def test_the_monotonicity_bound_would_catch_an_overstated_et_score():
    """Non-vacuity proof for the 90' <= final bound, aimed at an ET row for the
    same reason: those carry no equality check. Raising both 90' goals keeps the
    row LEVEL, so the loader's ET invariant still accepts it and only the bound
    objects — which is exactly the mis-curation shape it exists to catch."""
    df = load_regulation_table()
    i = df.index[df["went_et"]][0]
    df.loc[i, "h90"] += 1
    df.loc[i, "a90"] += 1
    merged = _merge_store(df)
    over = merged[(merged["h90"] > merged["home_score"])
                  | (merged["a90"] > merged["away_score"])]
    assert len(over) == 1
