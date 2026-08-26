"""The freshness sweep, held to the preregistration that precedes it.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_freshsweep.py -q

`reports/epl_freshness_prereg.md` (01f090a) fixes the estimand, the schedule,
the control, the refusals and the adoption rule BEFORE any harness existed.
These tests hold `epl.freshsweep` to that document, and they are shaped around
the four ways this particular run could produce a number nobody should believe:

* **A fit that has seen the fixture it prices.** The treatment arm's training
  set is a strict superset of the control arm's, so any leak biases the result
  toward freshness — the direction adoption would be granted on (§1.3 (b)).
  The leakage guard is tested on a synthetic frame, against the walk-forward's
  own `date < cutoff` rule, not against a restatement of it.
* **A partial run that scores anyway.** 507 fits across four shards is four
  ways to lose a fit quietly. The merge is tested to refuse a missing shard, a
  short shard, a poisoned shard and an unfrozen harness.
* **A resume that changes a number.** Resumability is only worth having if the
  resumed run is the same run; the demand is made on the canonical form, as
  §5.4 pre-states, and tested by interrupting one.
* **Arithmetic nobody checked.** The estimand and its bootstrap are tested
  against values computed by hand here, not against the harness's own output.
* **A run whose preconditions nobody checked.** §5.3's canary and §3.2's
  control are refusals, not documentation, and the tests are what make them so:
  the merge is held to both, and `--run` is held to them before it builds an
  engine.

CI HAS NO `data/`. Every test that needs a corpus builds its own — two seasons,
four blocks, openings and matchdays — and injects a deterministic stub fitter,
so **nothing here runs an ADVI fit**. (`wcmodel` IS imported, transitively:
`epl.freshsweep` reads A8's corpus pins from `epl.recalfit`, which imports it.
Nothing in this file calls its sampler.) The handful of tests that read the
pinned parquet or the committed prereg are guarded on the file's existence and
skip.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import freshsweep as fs
from epl import score as score_mod

#: The pinned corpus. Present on the machine that ran the walk and nowhere
#: else, so every test that reads it is guarded.
PINNED_CORPUS = Path("data/epl/fit/walkforward_predictions.parquet")

#: The preregistration this harness implements.
PREREG = Path("reports/epl_freshness_prereg.md")


# ==========================================================================
# a synthetic corpus: two seasons, four blocks, openings and matchdays
# ==========================================================================
def _corpus() -> pd.DataFrame:
    """A miniature walk-forward corpus with the real column contract.

    Two seasons x two blocks. Each block opens on a Monday and plays again
    later in the same ISO week, so every block carries fresh (own-day) and
    stale fixtures — the exact structure the estimand is defined over.
    """
    rows = []
    plan = [
        # season, block, date, n_fixtures
        ("2019/20", "2019/20|2019W32", "2019-08-05", 2),   # opening
        ("2019/20", "2019/20|2019W32", "2019-08-07", 2),   # +2 days
        ("2019/20", "2019/20|2019W33", "2019-08-12", 1),   # opening
        ("2019/20", "2019/20|2019W33", "2019-08-13", 2),   # +1 day
        ("2020/21", "2020/21|2020W38", "2020-09-14", 1),   # opening
        ("2020/21", "2020/21|2020W38", "2020-09-19", 2),   # +5 days
        ("2020/21", "2020/21|2020W39", "2020-09-21", 2),   # opening only
    ]
    k = 0
    for season, block, date, n in plan:
        for _ in range(n):
            k += 1
            p = [0.5 + 0.001 * k, 0.3 - 0.0005 * k, 0.2 - 0.0005 * k]
            p = [round(v / sum(p), 8) for v in p]
            rows.append({
                "match_id": f"m{k:03d}", "season": season, "block": block,
                "date": pd.Timestamp(date),
                "home_key": f"home{k}", "away_key": f"away{k}",
                "y": k % 3,
                "dc_home": p[0], "dc_draw": p[1], "dc_away": p[2],
            })
    df = pd.DataFrame(rows)
    df["dc_rps"] = score_mod.rps(df[["dc_home", "dc_draw", "dc_away"]].to_numpy(),
                                 df["y"].to_numpy())
    return df


def _stub_fitter(corpus: pd.DataFrame, *, nudge: float = 0.01, calls=None):
    """A deterministic stand-in for one matchday fit.

    Returns the corpus's own probabilities shifted by a fixed amount, so every
    delta the tests assert on is arithmetic somebody can do by hand. Records
    the fit points it was asked for, which is how "a completed key is skipped"
    is checked.
    """
    by_id = corpus.set_index("match_id")

    def fitter(point: fs.FitPoint) -> dict:
        if calls is not None:
            calls.append(point.cutoff)
        probs = []
        for mid in point.match_ids:
            row = by_id.loc[mid]
            p = np.array([row["dc_home"], row["dc_draw"], row["dc_away"]],
                         dtype=float)
            p = p + np.array([nudge, -nudge / 2.0, -nudge / 2.0])
            probs.append([round(float(v), 8) for v in p])
        return {
            "probs": probs,
            "n_training_matches": 100 + len(point.match_ids),
            "n_teams": 20, "cold_start_teams": [], "cold_start_z": {},
            "provisional_teams": [], "anchor_spec": "epl.elo/stub",
            "warnings": [], "unpriceable": [], "malformed": [],
            "health": {"all_finite": True, "sigma_positive": True,
                       "home_adv_sane": True},
            "seconds": 1.5,
            "latest_training_date": "1999-01-01",
            "n_training_matches_store": 100 + len(point.match_ids),
        }

    return fitter


def _run(tmp_path, corpus, points, **kw):
    calls = kw.pop("calls", None)
    fitter = kw.pop("fitter", None) or _stub_fitter(corpus, calls=calls)
    ledger = kw.pop("ledger", tmp_path / "shard_00_of_01.jsonl")
    return fs.run_fits(points, ledger, corpus, fitter=fitter, verbose=False,
                       **kw)


# ==========================================================================
# 1. the fit points — 507 dates that were never a cutoff
# ==========================================================================

def test_fit_points_exclude_every_block_opening_date():
    """Arm A fits the 507 dates that are NOT block-opening days (§2).

    An opening date already has a fit in the corpus; re-fitting it would price
    fixtures the corpus already priced from the same cutoff, which is the
    control (§3.2) and not the treatment.
    """
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    cutoffs = [p.cutoff for p in points]
    assert cutoffs == ["2019-08-07", "2019-08-13", "2020-09-19"]
    openings = set(fs.block_openings(corpus).values())
    assert not (set(cutoffs) & openings)


def test_fit_points_carry_exactly_that_date_s_fixtures_and_their_staleness():
    corpus = _corpus()
    points = {p.cutoff: p for p in fs.fit_points(corpus, check=False)}

    two = points["2019-08-07"]
    assert two.season == "2019/20"
    assert two.block == "2019/20|2019W32"
    assert two.block_cutoff == "2019-08-05"
    assert two.match_ids == ("m003", "m004")
    assert two.staleness_days == 2
    assert points["2019-08-13"].staleness_days == 1
    assert points["2020-09-19"].staleness_days == 5


def test_fit_points_cover_every_stale_fixture_exactly_once():
    """The denominator is fixed and no fixture may be dropped (§2)."""
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    priced = [m for p in points for m in p.match_ids]
    openings = fs.block_openings(corpus)
    stale = set(corpus.loc[
        corpus["date"].dt.strftime("%Y-%m-%d")
        != corpus["block"].map(openings), "match_id"])
    assert len(priced) == len(set(priced))
    assert set(priced) == stale


def test_the_opening_schedule_is_the_other_half_of_the_calendar():
    corpus = _corpus()
    matchday = fs.fit_points(corpus, check=False)
    opening = fs.fit_points(corpus, kind="opening", check=False)
    assert {p.cutoff for p in matchday} | {p.cutoff for p in opening} == set(
        corpus["date"].dt.strftime("%Y-%m-%d"))
    assert not ({p.cutoff for p in matchday} & {p.cutoff for p in opening})
    assert all(p.staleness_days == 0 for p in opening)


def test_a_corpus_of_the_wrong_shape_is_a_typed_refusal_not_a_smaller_run():
    """`ScheduleMismatch` (§5.1): the counts are pre-stated, so a corpus that
    does not produce them is a different corpus and not a smaller experiment."""
    corpus = _corpus()
    with pytest.raises(fs.ScheduleMismatch) as e:
        fs.fit_points(corpus, check=True)
    assert "507" in str(e.value)


# ==========================================================================
# 2. sharding — a partition, proved to be one
# ==========================================================================

def test_shards_partition_the_fit_points_exactly():
    """Union is everything, pairwise intersection is nothing (§5.1).

    A shard scheme that drops or duplicates a fit date produces a merge that is
    short or double-counted, and the merge's own key check is the only thing
    that would catch it — so the partition is proved here as well.
    """
    points = [fs.FitPoint(season="2019/20", block="b", cutoff=f"2019-01-{d:02d}",
                          block_cutoff="2019-01-01", match_ids=(f"m{d}",),
                          staleness_days=d)
              for d in range(1, 32)]
    for n in (1, 2, 3, 4, 7):
        shards = [fs.shard_points(points, i, n) for i in range(n)]
        union = [p for s in shards for p in s]
        assert len(union) == len(points)
        assert {p.cutoff for p in union} == {p.cutoff for p in points}
        for i in range(n):
            for j in range(i + 1, n):
                assert not ({p.cutoff for p in shards[i]}
                            & {p.cutoff for p in shards[j]})
        assert max(len(s) for s in shards) - min(len(s) for s in shards) <= 1


def test_a_shard_outside_its_own_count_is_refused():
    points = [fs.FitPoint("2019/20", "b", "2019-01-01", "2019-01-01", ("m",), 0)]
    with pytest.raises(fs.FreshnessError):
        fs.shard_points(points, 4, 4)
    with pytest.raises(fs.FreshnessError):
        fs.shard_points(points, -1, 4)


# ==========================================================================
# 3. the leakage guard — the one asymmetry with a direction
# ==========================================================================

def test_a_fixture_on_the_cutoff_date_is_absent_from_its_own_training_frame():
    """§1.3 (b) guard 1, on a synthetic frame, by the walk's own rule.

    `wcmodel.data.features.build` keeps `date < cutoff.normalize()`. So a
    fixture kicking off ON the matchday cutoff — the fixture being priced, and
    every other fixture that day — is unseen. This asserts the rule against a
    frame where a leak would be visible, rather than quoting the source line.
    """
    played = pd.DataFrame({
        "match_id": ["a", "b", "c", "d", "e"],
        "date": pd.to_datetime(["2019-08-01", "2019-08-06", "2019-08-07",
                                "2019-08-07", "2019-08-09"]),
    })
    seen = fs.visible_training_frame("2019-08-07", played)
    assert list(seen["match_id"]) == ["a", "b"]
    assert "c" not in set(seen["match_id"]) and "d" not in set(seen["match_id"])

    out = fs.assert_cutoff_clean("2019-08-07", played, ("c", "d"))
    assert out["n_training_matches"] == 2
    assert out["latest_training_date"] == "2019-08-06"


def test_a_priced_fixture_inside_the_training_frame_is_a_cutoff_leak():
    played = pd.DataFrame({
        "match_id": ["a", "b"],
        "date": pd.to_datetime(["2019-08-01", "2019-08-06"]),
    })
    with pytest.raises(fs.CutoffLeak) as e:
        fs.assert_cutoff_clean("2019-08-07", played, ("b",))
    assert "b" in str(e.value)


def test_a_fixture_that_does_not_kick_off_on_its_own_cutoff_is_a_cutoff_leak():
    """A matchday fit prices that matchday. A fixture dated elsewhere in the
    frame would be priced from a cutoff that is not its own date, which is the
    block fit — the other arm."""
    played = pd.DataFrame({
        "match_id": ["a", "b"],
        "date": pd.to_datetime(["2019-08-01", "2019-08-09"]),
    })
    with pytest.raises(fs.CutoffLeak):
        fs.assert_cutoff_clean("2019-08-07", played, ("b",))


def test_the_runner_checks_the_cutoff_before_it_trusts_a_fit(tmp_path):
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)[:1]
    played = pd.DataFrame({
        "match_id": list(corpus["match_id"]),
        "date": corpus["date"],
    })
    out = _run(tmp_path, corpus, points, played=played)
    assert out["n_fits"] == 1
    rows = fs.load_ledger(tmp_path / "shard_00_of_01.jsonl")
    assert rows[0]["fit"]["latest_training_date"] < rows[0]["cutoff"]


# ==========================================================================
# 4. the ledger — keyed, resumable, and byte-identical when resumed
# ==========================================================================

def test_one_row_per_fixture_carrying_both_arms_and_their_provenance(tmp_path):
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    _run(tmp_path, corpus, points)
    rows = fs.load_ledger(tmp_path / "shard_00_of_01.jsonl")

    assert len(rows) == 6                       # the synthetic corpus's stale set
    row = next(r for r in rows if r["match_id"] == "m003")
    assert row["cutoff"] == "2019-08-07"
    assert row["block_cutoff"] == "2019-08-05"
    assert row["staleness_days"] == 2
    assert row["seed"] == fs.SEED
    assert row["arm_b"]["source"].endswith("walkforward_predictions.parquet")
    assert row["arm_b"]["corpus_sha256"] == fs.CORPUS_SHA256
    assert row["arm_a"]["cutoff"] == "2019-08-07"

    corpus_row = corpus.set_index("match_id").loc["m003"]
    assert row["probs_block"] == [corpus_row["dc_home"], corpus_row["dc_draw"],
                                  corpus_row["dc_away"]]
    assert row["rps_block"] == pytest.approx(corpus_row["dc_rps"], abs=0)
    assert row["delta"] == pytest.approx(row["rps_fresh"] - row["rps_block"],
                                         abs=1e-15)


#: §5.2's list, transcribed from `reports/epl_freshness_prereg.md` and not from
#: the module: "`cutoff` (ISO date) · `seed` (20260611) · `config_sha256` (of
#: `epl/config_frozen.json`) · `realised_config_sha256` … · `n_training_matches`
#: · `n_teams` · `wall_seconds` · `match_ids` · `probs` (8 dp) ·
#: `cold_start_teams` · `provisional_teams` · `anchor_spec` · `warnings` ·
#: `unpriceable` · `health` · `harness_sha256` · `archive_rows` and
#: `archive_sha256` … · `blas_threads` · `shard_id`."
#: The value is where the row keeps it — `probs` is Arm A's `probs_fresh`, and
#: `shard_id` is on the row rather than in its `fit` block.
PREREG_5_2 = {
    "cutoff": "fit", "seed": "fit", "config_sha256": "fit",
    "realised_config_sha256": "fit", "n_training_matches": "fit",
    "n_teams": "fit", "wall_seconds": "fit", "match_ids": "fit",
    "cold_start_teams": "fit", "provisional_teams": "fit",
    "anchor_spec": "fit", "warnings": "fit", "unpriceable": "fit",
    "health": "fit", "harness_sha256": "fit", "archive_rows": "fit",
    "archive_sha256": "fit", "blas_threads": "fit",
    "probs_fresh": "row", "shard_id": "row",
}


def test_every_prereg_field_is_on_every_row(tmp_path):
    """§5.2 names what a fit row records. A field nobody wrote is a field
    nobody can check afterwards.

    The list is transcribed from the document, not read off the module: a test
    that asserted `REQUIRED_FIT_FIELDS` against itself would go green on a
    schema that had quietly dropped one of §5.2's fields, which is the only
    failure this test exists to catch.
    """
    corpus = _corpus()
    _run(tmp_path, corpus, fs.fit_points(corpus, check=False))
    rows = fs.load_ledger(tmp_path / "shard_00_of_01.jsonl")
    assert rows
    for row in rows:
        for field, where in PREREG_5_2.items():
            holder = row if where == "row" else row["fit"]
            assert field in holder, f"§5.2's {field!r} is not on the {where}"
        assert row["fit"]["seed"] == 20260611
        assert len(row["probs_fresh"]) == 3
        assert all(round(v, 8) == v for v in row["probs_fresh"])
        for field in fs.REQUIRED_ROW_FIELDS:
            assert field in row, field
        for field in fs.REQUIRED_FIT_FIELDS:
            assert field in row["fit"], field

    # ...and the schema the loader enforces must not be narrower than §5.2.
    named = {f for f, w in PREREG_5_2.items() if w == "fit"}
    assert named <= set(fs.REQUIRED_FIT_FIELDS)
    assert {f for f, w in PREREG_5_2.items() if w == "row"} <= \
        set(fs.REQUIRED_ROW_FIELDS)


def test_a_row_missing_a_required_field_is_a_schema_mismatch(tmp_path):
    corpus = _corpus()
    _run(tmp_path, corpus, fs.fit_points(corpus, check=False))
    path = tmp_path / "shard_00_of_01.jsonl"
    lines = path.read_text().splitlines()
    bad = json.loads(lines[0])
    bad.pop("rps_fresh")
    path.write_text("\n".join([json.dumps(bad)] + lines[1:]) + "\n")
    with pytest.raises(fs.SchemaMismatch):
        fs.load_ledger(path)


def test_a_completed_key_is_skipped_on_resume(tmp_path):
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    calls: list[str] = []
    _run(tmp_path, corpus, points[:2], calls=calls)
    assert calls == ["2019-08-07", "2019-08-13"]
    _run(tmp_path, corpus, points, calls=calls)
    assert calls == ["2019-08-07", "2019-08-13", "2020-09-19"]


def test_an_interrupted_run_resumes_to_a_byte_identical_canonical_form(tmp_path):
    """§5.4: the demand is on the canonical form, not the raw file.

    A row records its own wall clock and its own shard, and two runs will never
    agree on those — so the volatile fields are stripped, the rows are sorted,
    and THAT is what must be identical. Anything weaker would let a resumed run
    quietly produce a different number.
    """
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)

    whole = tmp_path / "whole.jsonl"
    _run(tmp_path, corpus, points, ledger=whole)

    part = tmp_path / "part.jsonl"
    _run(tmp_path, corpus, points[:1], ledger=part, shard_id="9/9")
    _run(tmp_path, corpus, points, ledger=part)

    a, b = fs.load_ledger(whole), fs.load_ledger(part)
    assert fs.canonical(a) == fs.canonical(b)
    assert fs.run_digest(a) == fs.run_digest(b)
    # ...and the raw files are NOT identical, so the demand above is doing work
    assert {r["shard_id"] for r in b} == {"9/9", "0/1"}
    assert whole.read_text() != part.read_text()


def test_the_canonical_form_drops_exactly_the_pre_stated_volatile_fields():
    assert fs._VOLATILE == ("wall_seconds", "fit_seconds", "seconds",
                            "shard_id", "started_at", "host")
    rows = [{"key": "k", "match_id": "m", "seconds": 1.0, "shard_id": "0/4",
             "started_at": "now", "host": "h", "delta": 0.5,
             "fit": {"wall_seconds": 9.9, "n_teams": 20}}]
    text = fs.canonical(rows)
    assert "seconds" not in text and "shard_id" not in text
    assert "started_at" not in text and '"host"' not in text
    assert '"delta":0.5' in text.replace(" ", "")
    assert '"n_teams":20' in text.replace(" ", "")


def test_two_rows_that_disagree_on_a_scored_field_are_a_row_conflict(tmp_path):
    corpus = _corpus()
    _run(tmp_path, corpus, fs.fit_points(corpus, check=False)[:1])
    path = tmp_path / "shard_00_of_01.jsonl"
    first = json.loads(path.read_text().splitlines()[0])
    first["rps_fresh"] = first["rps_fresh"] + 0.1
    with path.open("a") as fh:
        fh.write(json.dumps(first) + "\n")
    with pytest.raises(fs.RowConflict):
        fs.load_ledger(path)


def test_a_repeated_row_that_agrees_is_not_a_conflict(tmp_path):
    """Resuming after a partial write re-runs the fit and appends the same row
    again. A deterministic fit makes that harmless, and the loader must say so
    rather than refusing a run that is in fact intact."""
    corpus = _corpus()
    _run(tmp_path, corpus, fs.fit_points(corpus, check=False)[:1])
    path = tmp_path / "shard_00_of_01.jsonl"
    line = path.read_text().splitlines()[0]
    repeat = json.loads(line)
    repeat["seconds"] = 99.0                 # volatile: not part of the row
    with path.open("a") as fh:
        fh.write(json.dumps(repeat) + "\n")
    rows = fs.load_ledger(path)
    assert len([r for r in rows if r["match_id"] == repeat["match_id"]]) == 1


def test_a_truncated_final_line_is_re_run_rather_than_believed(tmp_path):
    """A crash mid-append leaves half a JSON object and no newline after it.

    That fit is incomplete, so the fragment is dropped and the fit is re-run.
    The fragment is removed rather than left in place because the NEXT append
    would otherwise glue itself onto it and turn one unreadable line into two —
    which is how a resumable log quietly becomes a corrupted one.
    """
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    _run(tmp_path, corpus, points[:2])
    path = tmp_path / "shard_00_of_01.jsonl"
    path.write_text(path.read_text()[:-25])
    calls: list[str] = []
    out = _run(tmp_path, corpus, points, calls=calls)
    assert out["repaired_bytes"] > 0
    assert points[1].cutoff in calls
    rows = fs.load_ledger(path)
    assert len(rows) == 6
    assert {r["cutoff"] for r in rows} == {p.cutoff for p in points}


def test_a_malformed_line_that_is_not_the_tail_is_a_corrupted_ledger(tmp_path):
    """Only an interrupted append can tear a ledger, and it can only tear the
    end of one. Anything else is damage, and damage is refused rather than
    silently skipped."""
    corpus = _corpus()
    _run(tmp_path, corpus, fs.fit_points(corpus, check=False))
    path = tmp_path / "shard_00_of_01.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(["{not json"] + lines) + "\n")
    with pytest.raises(fs.FreshnessError) as e:
        fs.load_ledger(path)
    assert "corrupted" in str(e.value)


# ==========================================================================
# 5. poison — a failed fit stops the shard and the merge
# ==========================================================================

def _boom(point: fs.FitPoint) -> dict:
    raise RuntimeError("ADVI fell over")


def test_a_failed_fit_writes_a_typed_poison_row_and_raises(tmp_path):
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    with pytest.raises(fs.FitFailed):
        _run(tmp_path, corpus, points, fitter=_boom)
    text = (tmp_path / "shard_00_of_01.jsonl").read_text()
    poison = [json.loads(l) for l in text.splitlines() if l.strip()]
    assert len(poison) == 1
    assert poison[0]["poison"] is True
    assert poison[0]["error_type"] == "FitFailed"
    assert "ADVI fell over" in poison[0]["error"]
    assert poison[0]["cutoff"] == points[0].cutoff


def test_a_shard_that_still_carries_poison_refuses_to_start(tmp_path):
    """Fail closed. Re-running over a poisoned ledger would leave the poison
    row in place, the merge would refuse anyway, and the operator would have
    paid for the fits twice to learn it."""
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    with pytest.raises(fs.FitFailed):
        _run(tmp_path, corpus, points, fitter=_boom)
    with pytest.raises(fs.ShardFailed) as e:
        _run(tmp_path, corpus, points)
    assert "poison" in str(e.value).lower()


def test_an_unpriceable_fixture_is_a_refusal_never_a_dropped_row(tmp_path):
    """§2: the denominator is fixed at 1,699 and Arm A sees strictly more data
    than Arm B, so an unpriceable fixture is a defect by construction."""
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)

    def missing(point):
        out = _stub_fitter(corpus)(point)
        out["unpriceable"] = [{"match_id": point.match_ids[0],
                               "why": "club absent from the posterior index"}]
        return out

    with pytest.raises(fs.UnpriceableFixture):
        _run(tmp_path, corpus, points, fitter=missing)


def test_an_unhealthy_posterior_is_a_fit_failure(tmp_path):
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)

    def sick(point):
        out = _stub_fitter(corpus)(point)
        out["health"]["sigma_positive"] = False
        return out

    with pytest.raises(fs.FitFailed):
        _run(tmp_path, corpus, points, fitter=sick)


def test_a_forecast_that_does_not_sum_to_one_is_a_fit_failure(tmp_path):
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)

    def skew(point):
        out = _stub_fitter(corpus)(point)
        out["probs"] = [[0.5, 0.4, 0.4] for _ in out["probs"]]
        return out

    with pytest.raises(fs.FitFailed):
        _run(tmp_path, corpus, points, fitter=skew)


def test_a_corpus_rps_that_does_not_re_derive_is_a_score_mismatch():
    """§2: Arm B's `dc_rps` is copied, and also recomputed from Arm B's own
    stored probabilities. On the pinned corpus the difference is 0.0; the check
    is a guard against a future corpus."""
    corpus = _corpus()
    corpus.loc[0, "dc_rps"] = corpus.loc[0, "dc_rps"] + 1e-9
    with pytest.raises(fs.ScoreMismatch):
        fs.check_corpus_scores(corpus)


# ==========================================================================
# 6. the merge — every shard, no poison, the pre-stated key set
# ==========================================================================

def _write_shards(tmp_path, corpus, *, shards=2, preconditions=True, **kw):
    points = fs.fit_points(corpus, check=False)
    if preconditions:                      # §5.3 and §3.2, on the record
        _preconditions(tmp_path)
    for i in range(shards):
        part = fs.shard_points(points, i, shards)
        _run(tmp_path, corpus, part, shard_id=f"{i}/{shards}",
             ledger=tmp_path / fs.shard_name(i, shards), **kw)
    return points


def _do_merge(tmp_path, corpus, points, *, shards=2, frozen=True):
    return fs.merge(shards=shards, directory=tmp_path, corpus=corpus,
                    write=False, expected=len(points),
                    expected_fixtures=sum(len(p.match_ids) for p in points),
                    harness_frozen=frozen)


def _merged(tmp_path, corpus, *, shards=2, frozen=True):
    points = _write_shards(tmp_path, corpus, shards=shards)
    return _do_merge(tmp_path, corpus, points, shards=shards, frozen=frozen)


def test_the_merge_takes_the_union_of_complete_shards(tmp_path):
    corpus = _corpus()
    out = _merged(tmp_path, corpus)
    assert out["n_fits"] == 3
    assert out["n_fixtures"] == 6
    assert out["shards"] == ["shard_00_of_02.jsonl", "shard_01_of_02.jsonl"]


def test_a_missing_shard_refuses_the_merge(tmp_path):
    """A shard whose ledger is not on disk is a shard that never finished, and
    its fits are not optional (§5.1)."""
    corpus = _corpus()
    points = _write_shards(tmp_path, corpus)
    (tmp_path / fs.shard_name(1, 2)).unlink()
    with pytest.raises(fs.ShardFailed) as e:
        _do_merge(tmp_path, corpus, points)
    assert "shard_01_of_02" in str(e.value)


def test_a_short_shard_refuses_the_merge(tmp_path):
    """`MergeIncomplete` (§5.1): the union's key set must equal the expected
    keys exactly — not a superset, not a subset."""
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    _preconditions(tmp_path)
    for i in range(2):
        part = fs.shard_points(points, i, 2)
        _run(tmp_path, corpus, part[:1] if i == 0 else part,
             shard_id=f"{i}/2", ledger=tmp_path / fs.shard_name(i, 2))
    with pytest.raises(fs.MergeIncomplete):
        fs.merge(shards=2, directory=tmp_path, corpus=corpus, write=False,
                 expected=len(points),
                 expected_fixtures=sum(len(p.match_ids) for p in points),
                 harness_frozen=True)


def test_a_poisoned_shard_refuses_the_merge(tmp_path):
    corpus = _corpus()
    points = _write_shards(tmp_path, corpus)
    with (tmp_path / fs.shard_name(0, 2)).open("a") as fh:
        fh.write(json.dumps({"poison": True, "error_type": "FitFailed",
                             "error": "boom", "cutoff": "2019-08-07",
                             "key": "k", "shard_id": "0/2"}) + "\n")
    with pytest.raises(fs.ShardFailed) as e:
        _do_merge(tmp_path, corpus, points)
    assert "2019-08-07" in str(e.value)


def test_the_merge_refuses_before_the_harness_hash_freeze_commit(tmp_path):
    """§6 step 3 and §7: not one fit of this experiment counts before the hash
    table exists, so a merge that would score them refuses instead."""
    corpus = _corpus()
    with pytest.raises(fs.FreshnessError) as e:
        _merged(tmp_path, corpus, frozen=False)
    assert "hash" in str(e.value).lower()


def test_a_row_produced_before_the_freeze_cannot_be_merged_after_it(tmp_path):
    """The freeze is a property of the ROW, not of the merge's clock. A fit run
    during the audit is stamped `harness_frozen: false` and stays out."""
    corpus = _corpus()
    points = fs.fit_points(corpus, check=False)
    _preconditions(tmp_path)
    for i in range(2):
        _run(tmp_path, corpus, fs.shard_points(points, i, 2),
             shard_id=f"{i}/2", ledger=tmp_path / fs.shard_name(i, 2),
             harness_frozen=(i == 1))
    with pytest.raises(fs.FreshnessError) as e:
        _do_merge(tmp_path, corpus, points)
    assert "harness_frozen" in str(e.value)


# ==========================================================================
# 7. the estimand — arithmetic somebody did by hand
# ==========================================================================

def _rows(deltas, blocks, seasons=None, staleness=None):
    seasons = seasons or ["2019/20"] * len(deltas)
    staleness = staleness or [1] * len(deltas)
    out = []
    for i, (d, b, s, k) in enumerate(zip(deltas, blocks, seasons, staleness)):
        out.append({"match_id": f"m{i}", "block": b, "season": s,
                    "staleness_days": k, "rps_block": 0.2,
                    "rps_fresh": 0.2 + d, "delta": d,
                    "probs_block": [0.5, 0.3, 0.2],
                    "probs_fresh": [0.5, 0.3, 0.2]})
    return out


def test_the_estimand_is_the_pooled_mean_of_the_paired_deltas():
    """§2: 'the mean over all 1,699 deltas, pooled over matches (not a mean of
    block means)'.

    (-0.001 + 0.003 - 0.001 + 0.0) / 4 = **0.00025**, and the two blocks here
    have sizes 3 and 1 so the other reading is visibly different: block A's
    mean is 0.001/3 and block B's is 0.0, giving (0.000333 + 0.0) / 2 =
    **0.000167**. The assertion is the pooled one.
    """
    rows = _rows([-0.001, 0.003, -0.001, 0.0], ["A", "A", "A", "B"])
    out = fs.estimand(rows, n_boot=200)
    assert out["n"] == 4
    assert out["mean"] == pytest.approx((-0.001 + 0.003 - 0.001 + 0.0) / 4)
    assert out["mean"] == pytest.approx(0.00025)
    assert out["n_blocks"] == 2
    assert out["sd"] == pytest.approx(
        float(np.std([-0.001, 0.003, -0.001, 0.0], ddof=1)))
    assert out["se_iid"] == pytest.approx(out["sd"] / 2.0)


def test_the_interval_is_the_projects_own_block_bootstrap_at_the_pinned_seed():
    rows = _rows([-0.001, 0.003, -0.001, 0.0, 0.002, -0.004],
                 ["A", "A", "B", "B", "C", "C"])
    out = fs.estimand(rows, n_boot=1000)
    lo, hi, nb = score_mod.block_bootstrap_ci(
        np.array([r["delta"] for r in rows]),
        [r["block"] for r in rows], n_boot=1000, alpha=0.05,
        seed=fs.BOOTSTRAP_SEED)
    assert out["ci95"] == [lo, hi]
    assert out["n_blocks"] == nb
    assert out["bootstrap"] == {"n_boot": 1000, "seed": fs.BOOTSTRAP_SEED,
                                "alpha": 0.05, "blocks": "season|ISO week",
                                "method": "percentile"}


def test_the_bootstrap_is_reproducible_under_the_pinned_seed():
    """The same rows and the same seed give the same interval, every time —
    and a different seed does not, which is what makes the first claim worth
    making. Thirty fixtures in ten blocks, so the percentile is not so coarse
    that two seeds land on the same order statistic by accident."""
    deltas = [round(0.001 * i - 0.015, 6) for i in range(30)]
    rows = _rows(deltas, [f"B{i // 3}" for i in range(30)])
    a = fs.estimand(rows, n_boot=2000)
    b = fs.estimand(rows, n_boot=2000)
    assert a["ci95"] == b["ci95"]
    assert a["bootstrap"]["seed"] == fs.BOOTSTRAP_SEED
    c = fs.estimand(rows, n_boot=2000, seed=fs.BOOTSTRAP_SEED + 1)
    assert c["ci95"] != a["ci95"]


def test_the_strata_are_the_three_pre_stated_ones_and_decide_nothing():
    rows = _rows([-0.001, 0.003, -0.002, 0.004, 0.005],
                 ["A", "A", "B", "B", "C"],
                 seasons=["2019/20"] * 3 + ["2020/21"] * 2,
                 staleness=[1, 2, 3, 5, 6])
    out = fs.estimand(rows, n_boot=200)
    strata = out["strata"]["staleness"]
    assert [s["stratum"] for s in strata] == ["1", "2", "3+"]
    assert [s["n"] for s in strata] == [1, 1, 3]
    assert strata[2]["mean"] == pytest.approx((-0.002 + 0.004 + 0.005) / 3)
    assert [s["stratum"] for s in out["strata"]["season"]] == ["2019/20",
                                                               "2020/21"]
    assert out["decides"] == "nothing"


def test_the_adoption_rule_is_both_conditions_and_neither_alone():
    """§4.1: `delta <= -0.00030` AND the CI's upper bound `< 0`."""
    assert fs.ADOPT_DELTA == -0.00030
    assert fs.adoption(-0.0004, [-0.0009, -0.0001]) == "ADOPT"
    assert fs.adoption(-0.0004, [-0.0009, +0.0001]) == "WEEKLY STANDS"
    assert fs.adoption(-0.0002, [-0.0009, -0.0001]) == "WEEKLY STANDS"
    assert fs.adoption(+0.0004, [+0.0001, +0.0009]) == "WEEKLY STANDS"
    assert fs.adoption(-0.00030, [-0.0009, -0.0000001]) == "ADOPT"


def test_the_movement_diagnostic_reports_the_probability_shift():
    rows = _rows([-0.001, 0.003], ["A", "A"])
    rows[0]["probs_fresh"] = [0.52, 0.29, 0.19]
    out = fs.estimand(rows, n_boot=200)
    assert out["movement"]["max_abs_prob_shift"] == pytest.approx(0.02)
    assert out["movement"]["mean_abs_prob_shift"] == pytest.approx(
        (0.02 + 0.01 + 0.01 + 0.0 + 0.0 + 0.0) / 6)


def test_the_estimand_refuses_a_denominator_it_was_not_promised():
    rows = _rows([-0.001, 0.003], ["A", "A"])
    with pytest.raises(fs.MergeIncomplete):
        fs.estimand(rows, n_boot=200, expected_fixtures=1699)


# ==========================================================================
# 8. the block-parity positive control
# ==========================================================================

def test_the_control_dates_are_the_twenty_the_prereg_printed():
    """§3.2 printed the list so the choice cannot move. The recipe is
    reproduced here and the printed list is the assertion."""
    if not PINNED_CORPUS.exists():
        pytest.skip("the pinned corpus is not in this checkout")
    corpus = fs.load_corpus()
    assert fs.control_dates(corpus) == [
        "2019-10-21", "2019-12-03", "2020-02-14", "2020-03-07", "2020-06-22",
        "2020-07-20", "2020-09-14", "2021-10-16", "2021-12-06", "2022-01-11",
        "2022-08-05", "2022-10-01", "2022-10-18", "2023-04-01", "2023-04-03",
        "2023-09-01", "2024-02-12", "2024-02-26", "2024-09-21", "2024-10-21"]


def test_the_control_demands_exact_equality_at_the_corpus_s_own_precision():
    """§3.2 rules exact equality at 8 decimals, not a tolerance."""
    corpus = _corpus()
    dates = [p.cutoff for p in fs.fit_points(corpus, kind="opening",
                                             check=False)]

    def echo(point):
        by_id = corpus.set_index("match_id")
        return {**_stub_fitter(corpus)(point),
                "probs": [[by_id.loc[m, "dc_home"], by_id.loc[m, "dc_draw"],
                           by_id.loc[m, "dc_away"]] for m in point.match_ids]}

    out = fs.run_control(dates=dates, corpus=corpus, fitter=echo, verbose=False)
    assert out["PASS"] is True
    assert out["n_probabilities"] == 18
    assert out["max_abs_prob_diff"] == 0.0
    assert out["tolerance"] == "exact equality at the corpus's 8 decimals"


def test_the_control_refuses_a_difference_in_the_eighth_decimal():
    corpus = _corpus()
    dates = [p.cutoff for p in fs.fit_points(corpus, kind="opening",
                                             check=False)][:1]

    def drift(point):
        by_id = corpus.set_index("match_id")
        probs = []
        for m in point.match_ids:
            probs.append([round(by_id.loc[m, "dc_home"] + 1e-8, 8),
                          by_id.loc[m, "dc_draw"], by_id.loc[m, "dc_away"]])
        return {**_stub_fitter(corpus)(point), "probs": probs}

    with pytest.raises(fs.ControlMismatch) as e:
        fs.run_control(dates=dates, corpus=corpus, fitter=drift, verbose=False)
    assert "1e-08" in str(e.value) or "1.0e-08" in str(e.value) \
        or "0.00000001" in str(e.value)


def test_the_control_runs_before_any_matchday_fit(tmp_path):
    """§3.2: 'The control runs FIRST; not one matchday fit is run until it
    passes.'

    Asserted as a REFUSAL rather than as a constant. `RUN_ORDER` now opens with
    §5.3's canary, so the old form of this test ("control" in RUN_ORDER[0])
    would have gone green on a harness that declared the order and enforced
    nothing — which is what it was doing.
    """
    assert fs.CONTROL_RUNS_FIRST is True
    assert fs.RUN_ORDER.index("control") < fs.RUN_ORDER.index("run")
    fs.run_canary(runner=lambda: _canary_record(True),
                  path=tmp_path / "canary.json")
    with pytest.raises(fs.ControlMismatch):
        fs.require_run_preconditions(directory=tmp_path)


# ==========================================================================
# 9. the pinned corpus, the frozen config, the harness freeze
# ==========================================================================

@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not in this checkout")
def test_the_pinned_corpus_reproduces_every_schedule_count_the_prereg_states():
    corpus = fs.load_corpus()
    points = fs.fit_points(corpus)                # check=True: the counts bind
    assert len(points) == fs.EXPECTED_FIT_DATES == 507
    assert sum(len(p.match_ids) for p in points) == fs.EXPECTED_STALE == 1699
    assert len(fs.block_openings(corpus)) == fs.EXPECTED_BLOCKS == 212
    assert corpus["date"].nunique() == fs.EXPECTED_DATES == 719
    assert max(p.staleness_days for p in points) == 6


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not in this checkout")
def test_the_corpus_is_checked_by_digest_before_anything_is_computed(tmp_path):
    bad = tmp_path / "corpus.parquet"
    fs.load_corpus().head(10).to_parquet(bad)
    with pytest.raises(fs.CorpusDigestMismatch):
        fs.load_corpus(bad)
    with pytest.raises(fs.CorpusMissing):
        fs.load_corpus(tmp_path / "nowhere.parquet")


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not in this checkout")
def test_the_stored_rps_re_derives_from_the_stored_probabilities():
    out = fs.check_corpus_scores(fs.load_corpus())
    assert out["max_abs_diff"] == 0.0
    assert out["n"] == 2280


def test_the_corpus_pins_are_a8_s_own_constants_not_a_second_copy():
    """§0: 'This experiment adopts the same constants rather than restating
    them, so there is one place where "which corpus" is defined.'"""
    from epl import recalfit
    assert fs.CORPUS_SHA256 is recalfit.CORPUS_SHA256
    assert fs.CORPUS_PATH == recalfit.CORPUS_PATH
    assert fs.CORPUS_ROWS is recalfit.CORPUS_ROWS
    assert fs.CORPUS_SEASONS is recalfit.CORPUS_SEASONS


def test_the_seed_is_one_constant_and_not_derived_per_cutoff():
    """§2: 'seed 20260611 — the seed is ONE CONSTANT, epl/walkforward.py does
    not derive it per cutoff'."""
    assert fs.SEED == 20260611
    keys = {fs.fit_key(d, config_sha="abc") for d in
            ("2019-08-07", "2020-01-01", "2024-05-19")}
    assert all(f"|{fs.SEED}|" in k for k in keys)
    assert len(keys) == 3


def test_the_resampling_constants_are_transcribed_from_the_document():
    """§2 prints B = 10,000, alpha = 0.05 and resampling seed 20260814; §3.2's
    recipe is `default_rng(20260826).choice(212, size=20, replace=False)`; §0.1
    prints the schedule counts and the 56 control fixtures; §4.1 the threshold.

    The literals here are the DOCUMENT'S, not the module's: every other
    assertion about the bootstrap compares against `fs.BOOTSTRAP_SEED` itself,
    so a drifted constant would re-derive those assertions from its own new
    value and go green (the 827fcf7 pattern, and the audit's e2 mutation:
    `BOOTSTRAP_SEED = 20260815` passed the whole file). §7 names "a second
    bootstrap seed" as an invalidation; this is the line that enforces it."""
    assert fs.BOOTSTRAP_SEED == 20260814
    assert fs.N_BOOT == 10_000
    assert fs.ALPHA == 0.05
    assert fs.CONTROL_SEED == 20260826
    assert fs.N_CONTROL_DATES == 20
    assert fs.ADOPT_DELTA == -0.00030
    assert fs.MAX_STALENESS_DAYS == 6
    assert (fs.EXPECTED_BLOCKS, fs.EXPECTED_DATES, fs.EXPECTED_FIT_DATES,
            fs.EXPECTED_STALE, fs.EXPECTED_FRESH,
            fs.EXPECTED_CONTROL_FIXTURES) == (212, 719, 507, 1699, 581, 56)


@pytest.mark.skipif(not Path("epl/config_frozen.json").exists(),
                    reason="no frozen config in this checkout")
def test_a_config_that_is_not_the_frozen_one_is_a_typed_refusal(tmp_path):
    assert fs.config_sha256() == fs.CONFIG_SHA256
    other = tmp_path / "config.json"
    other.write_text('{"seed": 1}\n')
    with pytest.raises(fs.ConfigNotFrozen):
        fs.assert_config_frozen(other)


def test_the_harness_freeze_is_read_from_the_committed_record_not_asserted():
    """§6: the hash table is a committed fact about the harness, and the run
    reads it rather than believing itself."""
    status = fs.harness_freeze_status()
    assert set(status) >= {"frozen", "where", "files"}
    assert isinstance(status["frozen"], bool)


@pytest.mark.skipif(not PREREG.exists(), reason="reports/ is not in this checkout")
def test_the_freeze_note_must_name_every_harness_file_with_its_own_digest(tmp_path):
    note = tmp_path / "note.md"
    digests = {f: fs.sha256_file(Path(f)) for f in fs.HARNESS_FILES}
    note.write_text(
        "## Harness hashes\n\n"
        + "".join(f"| `{f}` | {len(Path(f).read_text().splitlines())} | "
                  f"`{d}` |\n" for f, d in digests.items())
        + f"\nschema `{fs.SCHEMA_ID}`\n")
    status = fs.harness_freeze_status(sources=[note])
    assert status["frozen"] is True
    assert set(status["files"]) == set(fs.HARNESS_FILES)

    stale = tmp_path / "stale.md"
    stale.write_text(note.read_text().replace(digests[fs.HARNESS_FILES[0]],
                                              "0" * 64))
    bad = fs.harness_freeze_status(sources=[stale])
    assert bad["frozen"] is False
    assert "differs" in bad["why"]

    with pytest.raises(fs.FreshnessError):
        fs.require_harness_freeze(sources=[stale])


def test_the_harness_files_are_the_two_files_that_can_change_a_number():
    assert fs.HARNESS_FILES == ("epl/freshsweep.py",
                                "epl/tests/test_freshsweep.py")
    assert fs.SCHEMA_ID == "epl-freshness-1"


# ==========================================================================
# 10. the scope boundary
# ==========================================================================

def test_the_harness_writes_nothing_the_prereg_forbids():
    """§6: the run writes `data/epl/fit/`, `reports/epl_freshness_result.*`
    and nothing else. Asserted on the module's own declared surface, which is
    what the CLI uses."""
    written = {str(p) for p in fs.WRITES}
    for forbidden in ("src/", "scripts/", "site/", "tools/", ".github/",
                      "epl/season/points_adjustments.jsonl",
                      "data/epl/sim/retro_r1.jsonl",
                      "reports/matchboard_scorecard.jsonl",
                      "reports/epl_recal_shadow.jsonl",
                      "walkforward_predictions.parquet"):
        assert not any(forbidden in w for w in written), forbidden
    assert any("data/epl/fit" in w for w in written)


def test_no_betting_vocabulary_anywhere_in_the_harness():
    """The house rule, and the one column family this experiment never reads:
    the corpus's `market_*` prices enter neither arm, neither stratum, nor the
    movement diagnostic."""
    text = Path("epl/freshsweep.py").read_text().lower()
    for word in ("wager", "bankroll", "punter", "bookmaker", "accumulator",
                 "edge over the market", "market_home", "market_rps"):
        assert word not in text, word


# ==========================================================================
# 11. the preconditions — the canary, and the control that runs first
# ==========================================================================

def _canary_record(ok: bool = True) -> dict:
    """The shape `epl.walkforward.point_in_time_canary` actually returns."""
    return {"cutoff": "2022-01-01", "later": "2023-01-01",
            "n_rewritten": 900, "n_fixtures_compared": 10,
            "forecasts_bit_identical_before_cutoff": ok,
            "positive_control_forecasts_moved_after_cutoff": True,
            "max_abs_diff_before_cutoff": 0.0 if ok else 0.3149,
            "max_abs_diff_positive_control": 0.812, "PASS": ok}


def _preconditions(tmp_path, *, control_pass=True, dates=None,
                   canary_pass=True) -> None:
    """Both §5 preconditions on the record, where the merge reads them."""
    (tmp_path / "canary.json").write_text(
        json.dumps(_canary_record(canary_pass)) + "\n")
    (tmp_path / "control.json").write_text(json.dumps({
        "schema": fs.SCHEMA_ID, "PASS": control_pass,
        "dates": list(dates or ["2019-08-05"]),
        "max_abs_prob_diff": 0.0, "n_probabilities": 18}) + "\n")


def test_the_canary_is_run_as_a_precondition_and_written_to_the_record(tmp_path):
    """§5.3: 'run once as a precondition, at its default cutoff, and its full
    dict is written into the run artifact'."""
    path = tmp_path / "canary.json"
    out = fs.run_canary(runner=lambda: _canary_record(True), path=path)
    assert out["PASS"] is True
    written = json.loads(path.read_text())
    assert written["max_abs_diff_positive_control"] == 0.812
    assert written["max_abs_diff_before_cutoff"] == 0.0
    assert fs.require_canary(path)["PASS"] is True


def test_a_canary_that_does_not_pass_stops_the_run_before_a_single_fit(tmp_path):
    """§5.1: `PASS: false` is `CanaryFailed` and the run does not start. The
    failing dict still lands on the record — a refusal is reported, not hidden."""
    path = tmp_path / "canary.json"
    with pytest.raises(fs.CanaryFailed) as e:
        fs.run_canary(runner=lambda: _canary_record(False), path=path)
    assert "0.3149" in str(e.value)
    assert json.loads(path.read_text())["PASS"] is False


def test_a_missing_canary_is_a_refusal_and_not_a_default(tmp_path):
    with pytest.raises(fs.CanaryFailed) as e:
        fs.require_canary(tmp_path / "nowhere.json")
    assert "canary" in str(e.value).lower()


def test_a_failed_canary_on_the_record_refuses_every_later_process(tmp_path):
    """The canary runs once, in one process, and the shards read its record.
    A record that says FAIL has to refuse them — otherwise 'run once' would
    mean 'checked by whoever happened to run it'."""
    path = tmp_path / "canary.json"
    path.write_text(json.dumps(_canary_record(False)) + "\n")
    with pytest.raises(fs.CanaryFailed) as e:
        fs.require_canary(path)
    assert "0.3149" in str(e.value)

    path.write_text("{not json")
    with pytest.raises(fs.CanaryFailed) as e:
        fs.require_canary(path)
    assert "not readable JSON" in str(e.value)


def test_no_matchday_fit_starts_until_the_control_has_passed(tmp_path):
    """§3.2: 'The control runs FIRST; not one matchday fit is run until it
    passes.' Declaring the order in a constant is not enforcing it."""
    canary = tmp_path / "canary.json"
    fs.run_canary(runner=lambda: _canary_record(True), path=canary)
    control = tmp_path / "control.json"

    with pytest.raises(fs.ControlMismatch) as e:
        fs.require_run_preconditions(canary_path=canary, control_path=control)
    assert "has not run" in str(e.value)

    control.write_text(json.dumps({"PASS": False, "dates": ["2019-08-05"],
                                   "max_abs_prob_diff": 1e-8}) + "\n")
    with pytest.raises(fs.ControlMismatch):
        fs.require_run_preconditions(canary_path=canary, control_path=control)

    control.write_text(json.dumps({"PASS": True, "dates": ["2019-08-05"],
                                   "max_abs_prob_diff": 0.0}) + "\n")
    ok = fs.require_run_preconditions(canary_path=canary, control_path=control)
    assert ok["control"]["PASS"] is True and ok["canary"]["PASS"] is True


def test_a_control_that_covers_fewer_dates_than_demanded_is_refused(tmp_path):
    """A three-date smoke control is not the twenty §3.2 pre-states, and the
    preregistered run demands all of them by name."""
    canary = tmp_path / "canary.json"
    fs.run_canary(runner=lambda: _canary_record(True), path=canary)
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"PASS": True, "dates": ["2019-08-05"]}) + "\n")
    with pytest.raises(fs.ControlMismatch) as e:
        fs.require_run_preconditions(canary_path=canary, control_path=control,
                                     dates=["2019-08-05", "2019-08-12"])
    assert "2019-08-12" in str(e.value)


def test_the_canary_is_the_first_precondition_and_the_control_the_second():
    """§5.3 makes the canary a precondition of the run; §3.2 makes the control
    the first thing that fits. Both come before a matchday fit."""
    assert fs.RUN_ORDER == ("canary", "control", "run", "merge")
    assert fs.RUN_ORDER.index("control") < fs.RUN_ORDER.index("run")
    assert fs.CONTROL_RUNS_FIRST is True


def test_the_merge_refuses_a_run_whose_preconditions_are_not_on_the_record(tmp_path):
    """§5.1's refusals are preconditions of the NUMBER, not of the wall clock:
    a merge that scored fits taken without a passing canary and a passing
    control would publish an estimand nobody checked."""
    corpus = _corpus()
    points = _write_shards(tmp_path, corpus, preconditions=False)

    with pytest.raises(fs.CanaryFailed):
        _do_merge(tmp_path, corpus, points)

    _preconditions(tmp_path, control_pass=False)
    with pytest.raises(fs.ControlMismatch):
        _do_merge(tmp_path, corpus, points)

    _preconditions(tmp_path)
    out = _do_merge(tmp_path, corpus, points)
    assert out["canary"]["PASS"] is True
    assert out["control"]["PASS"] is True


def _pin(monkeypatch) -> None:
    """§3.2's other pre-stated condition, declared by the test that needs it:
    a control that will run real fits refuses an unpinned process."""
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(var, "1")


def test_the_control_enters_the_fast_panel_context_it_pre_states(monkeypatch):
    """§3.2's pre-stated condition is `fast_panel=True`. An engine that is
    built and never entered runs the control outside the context the document
    fixed — and pays ~50 s a fit for the privilege."""
    _pin(monkeypatch)
    corpus = _corpus()
    by_id = corpus.set_index("match_id")
    entered: list[str] = []

    class FakeEngine:
        def __init__(self, *a, **kw):
            entered.append("built")

        def __enter__(self):
            entered.append("enter")
            return self

        def __exit__(self, *exc):
            entered.append("exit")
            return False

        def fit(self, point):
            return {**_stub_fitter(corpus)(point),
                    "probs": [[by_id.loc[m, "dc_home"], by_id.loc[m, "dc_draw"],
                               by_id.loc[m, "dc_away"]]
                              for m in point.match_ids]}

    monkeypatch.setattr(fs, "Engine", FakeEngine)
    dates = [p.cutoff for p in fs.fit_points(corpus, kind="opening",
                                             check=False)]
    out = fs.run_control(dates=dates, corpus=corpus, verbose=False)
    assert out["PASS"] is True
    assert entered == ["built", "enter", "exit"]


def test_an_engine_the_caller_owns_is_not_entered_twice(monkeypatch):
    """`main --run` opens the context itself and passes the engine in; entering
    it again here would nest `config_read_once` inside itself."""
    _pin(monkeypatch)
    corpus = _corpus()
    by_id = corpus.set_index("match_id")
    entered: list[str] = []

    class Owned:
        def __enter__(self):
            entered.append("enter")
            return self

        def __exit__(self, *exc):
            return False

        def fit(self, point):
            return {**_stub_fitter(corpus)(point),
                    "probs": [[by_id.loc[m, "dc_home"], by_id.loc[m, "dc_draw"],
                               by_id.loc[m, "dc_away"]]
                              for m in point.match_ids]}

    dates = [p.cutoff for p in fs.fit_points(corpus, kind="opening",
                                             check=False)][:1]
    out = fs.run_control(dates=dates, corpus=corpus, engine=Owned(),
                         verbose=False)
    assert out["PASS"] is True
    assert entered == []


def test_the_canary_artifact_is_inside_the_directory_the_run_writes():
    assert fs.CANARY_JSON.parent == fs.FRESHNESS_DIR
    assert fs.CANARY_JSON in fs.WRITES


def test_main_prints_a_typed_stop_and_exits_two(monkeypatch, capsys, tmp_path):
    """§5.1: 'main() prints "STOP: …" naming the type and the offending key,
    and exits 2 — the convention A8's `RecalError` set.'

    Run against an audit directory, because the preregistered one refuses
    before the corpus is even read while §6's freeze commit is outstanding.
    """
    def boom(*a, **kw):
        raise fs.CorpusMissing("the pinned parquet is not on disk")

    monkeypatch.setattr(fs, "load_corpus", boom)
    code = fs.main(["--control", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 2
    assert out.startswith("STOP: CorpusMissing: ")


def test_main_refuses_a_matchday_fit_with_no_preconditions(monkeypatch, capsys,
                                                           tmp_path):
    """The CLI is where the order actually has to hold: `--run` reads the two
    records before it builds an engine, because building one costs real time
    and a run that is going to be refused should be refused before it pays.

    Pinned to the PRE-FREEZE branch of `--run`, the way the two directory-guard
    tests below pin the same function: once §6's freeze note lands in the real
    prereg, the frozen branch demands §3.2's twenty control dates by name, and
    `control_dates` on this ten-fixture corpus is a typed refusal of its own —
    the subject here is the order, not the freeze state, and a test that read
    the repository's freeze status would fail on the commit that freezes it.
    """
    corpus = _corpus()
    monkeypatch.setattr(fs, "harness_freeze_status",
                        lambda *a, **k: {"frozen": False, "why": "no table",
                                         "files": {}, "where": None,
                                         "missing": list(fs.HARNESS_FILES)})
    monkeypatch.setattr(fs, "load_corpus", lambda *a, **kw: corpus)
    monkeypatch.setattr(fs, "check_corpus_scores", lambda *a, **kw: {})
    monkeypatch.setattr(fs, "fit_points", lambda *a, **kw: [])
    monkeypatch.setattr(fs, "Engine", lambda *a, **kw: pytest.fail(
        "an engine was built before the preconditions were checked"))

    code = fs.main(["--run", "--dir", str(tmp_path)])
    assert code == 2
    assert capsys.readouterr().out.startswith("STOP: CanaryFailed: ")


# ==========================================================================
# 12. the BLAS pin — a property of the worker, not of every importer
# ==========================================================================

def test_importing_the_harness_does_not_repin_the_process(monkeypatch):
    """The pin belongs to `python -m epl.freshsweep`, which sets it before
    numpy loads. A module that rewrote the environment on IMPORT would change
    the behaviour of every library imported after it in a process that never
    asked — this test suite among them — and would not reach the BLAS pool it
    was aimed at anyway, because that pool is already loaded by then."""
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    threads = fs.blas_threads()
    assert threads["entry_point"] is False
    assert threads["pinned_before_numpy"] is False
    assert threads["OMP_NUM_THREADS"] is None

    with pytest.raises(fs.FreshnessError) as e:
        fs.assert_blas_pinned("a worker")
    assert "OMP_NUM_THREADS" in str(e.value)

    _pin(monkeypatch)
    assert fs.assert_blas_pinned("a worker")["OMP_NUM_THREADS"] == "1"


def test_a_control_that_will_run_real_fits_refuses_an_unpinned_process(monkeypatch):
    """§3.2's condition, checked where the fits are: 'the control runs ... with
    OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1 per worker'."""
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    corpus = _corpus()
    dates = [p.cutoff for p in fs.fit_points(corpus, kind="opening",
                                             check=False)][:1]
    with pytest.raises(fs.FreshnessError) as e:
        fs.run_control(dates=dates, corpus=corpus, verbose=False)
    assert "BLAS thread" in str(e.value)


def test_the_preregistered_directory_is_closed_to_a_pre_freeze_audit(
        monkeypatch, capsys):
    """§6 step 3 is "only then does the first fit run", and the canary and the
    control ARE fits — 4 and 20 of them. The ledger was guarded from the start;
    its two siblings were not, and a pre-freeze `control.json` left in the run
    directory is exactly what a later `--run` reads as *the control passed*."""
    monkeypatch.setattr(fs, "harness_freeze_status",
                        lambda *a, **k: {"frozen": False, "why": "no table",
                                         "files": {}, "where": None,
                                         "missing": list(fs.HARNESS_FILES)})
    monkeypatch.setattr(fs, "run_canary", lambda *a, **k: pytest.fail(
        "the canary ran before the directory was checked"))
    monkeypatch.setattr(fs, "load_corpus", lambda *a, **k: pytest.fail(
        "the control loaded a corpus before the directory was checked"))

    for argv in (["--canary"], ["--control"]):
        assert fs.main(argv) == 2
        out = capsys.readouterr().out
        assert out.startswith("STOP: FreshnessError: refusing to write ")
        assert "--dir" in out


def test_an_audit_directory_of_its_own_is_not_refused(tmp_path, monkeypatch,
                                                      capsys):
    """The other half of the rule: an audit is legitimate and expected."""
    monkeypatch.setattr(fs, "harness_freeze_status",
                        lambda *a, **k: {"frozen": False, "why": "no table",
                                         "files": {}, "where": None,
                                         "missing": list(fs.HARNESS_FILES)})
    monkeypatch.setattr(fs, "run_canary",
                        lambda **k: {"PASS": True, "path": str(k.get("path"))})
    assert fs.main(["--canary", "--dir", str(tmp_path)]) == 0
    assert "PASS" in capsys.readouterr().out


# ==========================================================================
# 12. the archive digest — the one that binds the scores it names
# ==========================================================================
#: `archive_sha256` sits on every ledger row to answer one question: *was the
#: results archive the same object when this fit ran?* Row-3 of that answer is
#: the SCORES — an archive whose 2-1 became a 3-1 trains a different model and
#: must produce a different digest, or the field is decoration. The first
#: implementation asked for `home_score`/`away_score`, which this schema has
#: never had (`epl/schema.py`: `fthg`/`ftag`), and the column filter silently
#: dropped both — so the digest bound ids and dates and nothing else, and every
#: score in the archive could change under it without moving a hex digit.
def _archive_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "match_id": ["a", "b", "c"],
        "date": pd.to_datetime(["2019-08-05", "2019-08-06", "2019-08-07"]),
        "home_key": ["h1", "h2", "h3"], "away_key": ["a1", "a2", "a3"],
        "fthg": [2, 1, 0], "ftag": [1, 1, 3],
        "ftr": ["H", "D", "A"], "played": [True, True, True],
    })


def test_the_archive_digest_binds_the_scores_it_is_asked_to_bind():
    """A changed score MUST change the digest."""
    played = _archive_frame()
    before = fs.archive_digest(played)

    moved = played.copy()
    moved.loc[0, "fthg"] = 3            # 2-1 becomes 3-1: a different archive
    assert fs.archive_digest(moved) != before

    moved_away = played.copy()
    moved_away.loc[2, "ftag"] = 4       # 0-3 becomes 0-4
    assert fs.archive_digest(moved_away) != before

    # and it is still stable under a re-read that changes nothing
    assert fs.archive_digest(_archive_frame()) == before


def test_the_archive_digest_refuses_a_frame_missing_the_fields_it_names():
    """The defect was a SILENT drop. A missing column is now a refusal."""
    played = _archive_frame().drop(columns=["ftag"])
    with pytest.raises(fs.SchemaMismatch, match="ftag"):
        fs.archive_digest(played)
