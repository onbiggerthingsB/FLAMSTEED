"""The evidence-mass widening harness, held to the preregistration that precedes it.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_evwiden.py -q

`reports/epl_widening_prereg.md` (f26b760) fixes the rule, its one frozen
constant, the estimand, both intervals, the two-gate adoption rule, the refusal
semantics and the scope BEFORE any harness existed. These tests hold
`epl.evwiden` to that document, and they are shaped around the six ways this
particular experiment could produce a number nobody should believe:

* **A treatment that is not the treatment.** The whole design rests on §0.2:
  mechanism (c) is a predict-time mix, the fitted posterior is arm-invariant, and
  a treated fixture receives EXACTLY the one incumbent mix at alpha = 0.5. The
  direction canary checks that against `wcmodel.model.widening.inflate_predictive`
  itself, on a real grid, rather than against a restatement of it.
* **A population that moved.** 85 thin fixtures, 52 treated, 51 cells, 78
  openings, 16 table cells — every one of them pre-stated. The membership tests
  compute the counts from the rule and refuse the harness's own arithmetic if it
  disagrees; the digest tests make a reordering unable to hide.
* **A predicate that leaks.** `e(t, C)` is a sum over archive rows and the strict
  `<` is the only thing that makes it point-in-time. The evidence canary is
  tested in BOTH legs, including the positive control, because a canary that
  cannot fail is not a canary.
* **A partial run that scores anyway.** The merge is tested against a missing
  shard, a short shard, a poisoned shard, a stray key, a substituted fixture, an
  unfrozen harness and a duplicated row that disagrees.
* **A resume that changes a number.** Resumability is only worth having if the
  resumed run is the same run; the demand is made on the canonical form, as §5.2
  pre-states, and tested by interrupting one.
* **Arithmetic nobody checked.** The estimand, the grid assembly, the
  full-population identity and both gates are tested against values computed BY
  HAND here, not against the harness's own output.

CI HAS NO `data/`, AND NOTHING HERE RUNS A FIT. Every test builds its own
synthetic corpus, archive and ledger and injects a deterministic stub fitter, so
no ADVI sampler runs in this file. (`wcmodel` IS imported, transitively:
`epl.evwiden` reads A8's corpus pins from `epl.recalfit`. The direction-canary
test calls `wcmodel.model.widening.inflate_predictive`, which is arithmetic on a
grid, not a fit.) The handful of tests that read a pinned artifact or the
committed preregistration are guarded on the file's existence and skip.

§5.3'S SEEDED DEFECTS RUN HERE AND ONLY HERE. "The adversarial audit seeds each
defect class of §5.1 alone and demands red under the harness's own tests — **on
synthetic corpora only**." Each `test_seeded_*` below is one defect class, alone.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import evwiden as ew
from epl import score as score_mod

#: The pinned artifacts. Present on the machine that ran the walk and nowhere
#: else, so every test that reads one is guarded.
PINNED_CORPUS = Path("data/epl/fit/walkforward_predictions.parquet")
PINNED_ARCHIVE = Path("data/epl/matches.parquet")
PINNED_LEDGER = Path("data/epl/fit/walkforward_ledger.jsonl")

#: The preregistration this harness implements.
PREREG = Path("reports/epl_widening_prereg.md")


# ==========================================================================
# the synthetic world: an archive whose `e` values are chosen, not discovered
# ==========================================================================

CUT_A = "2020-01-06"          # season one, block one
CUT_B = "2020-01-13"          # season one, block two
CUT_C = "2021-01-04"          # season two, block one
CUT_D = "2020-01-20"          # season one, block three — `stale` sits it out

#: Four clubs with four evidence profiles, by construction:
#:   rich  — 40 recent matches            -> e well above every grid point
#:   mid   — a handful of recent matches  -> e in the single digits
#:   stale — one match ten half-lives ago -> e ~ 0.001, the Hull shape
#:   cold  — no archive rows at all       -> e = 0, the Coventry shape
CLUBS = ("rich", "mid", "stale", "cold")


def _archive() -> pd.DataFrame:
    """A played frame with hand-placed dates, so every `e` is predictable."""
    base = pd.Timestamp(CUT_A)
    rows = []
    k = 0

    def add(home: str, away: str, days_before: int, when: pd.Timestamp = base):
        nonlocal k
        k += 1
        rows.append({"match_id": f"a{k:04d}",
                     "date": when - pd.Timedelta(days=int(days_before)),
                     "home_key": home, "away_key": away,
                     "fthg": k % 4, "ftag": (k + 1) % 3, "played": True,
                     "season": "hist"})

    # `rich`: 40 matches in the year before CUT_A, alternating venue.
    for i in range(40):
        add("rich", "mid" if i % 4 == 0 else "other", 5 + 8 * i)
    # `mid` gets only those ten away games plus two of its own.
    add("mid", "other", 10)
    add("other", "mid", 20)
    # `stale`: one match 3650 days back — 0.5 ** 10 = 0.0009765625.
    add("stale", "other", 3650)
    # `cold` appears nowhere before the cutoffs.
    # An archive covers more than the corpus scores, so it also carries rows
    # AFTER every cutoff here. They change no `e` — which is the property the
    # evidence canary's negative leg exists to prove, and it cannot prove it
    # against a frame that has no future in it.
    for i in range(4):
        add(CLUBS[i], CLUBS[(i + 1) % 4], -(60 + 30 * i),
            when=pd.Timestamp(CUT_C))
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame


def _corpus() -> pd.DataFrame:
    """A miniature walk-forward corpus with the real column contract.

    Three blocks over two seasons. Every fixture pairs a club whose `e` is known
    with another, so which fixtures are thin at which grid point is arithmetic
    rather than something the harness gets to decide.
    """
    plan = [
        # season, block, cutoff, home, away
        ("2019/20", "2019/20|2020W02", CUT_A, "rich", "mid"),
        ("2019/20", "2019/20|2020W02", CUT_A, "stale", "cold"),
        ("2019/20", "2019/20|2020W02", CUT_A, "rich", "cold"),
        ("2019/20", "2019/20|2020W03", CUT_B, "mid", "stale"),
        ("2019/20", "2019/20|2020W03", CUT_B, "rich", "rich"),
        ("2020/21", "2020/21|2021W01", CUT_C, "rich", "mid"),
        ("2020/21", "2020/21|2021W01", CUT_C, "cold", "rich"),
        # a block whose season includes `stale` but whose fixtures do not: the
        # §2.2 distinction between the 51 flagged CELLS and the 47 that reach a
        # fixture only exists because a club can be evidence-thin in a week it
        # does not play.
        ("2019/20", "2019/20|2020W04", CUT_D, "rich", "mid"),
    ]
    rows = []
    for k, (season, block, cutoff, home, away) in enumerate(plan, 1):
        p = np.array([0.5 + 0.01 * k, 0.3 - 0.004 * k, 0.2 - 0.006 * k])
        p = np.round(p / p.sum(), 8)
        p[2] = round(1.0 - p[0] - p[1], 8)
        y = k % 3
        rows.append({
            "match_id": f"m{k:03d}", "season": season, "block": block,
            "date": pd.Timestamp(cutoff), "home_key": home, "away_key": away,
            "y": y, "dc_home": p[0], "dc_draw": p[1], "dc_away": p[2],
            "dc_rps": float(score_mod.rps(np.array([p]), np.array([y]))[0]),
        })
    return pd.DataFrame(rows)


def _ledger(**override) -> dict[str, set[str]]:
    """The incumbent provisional sets the "published fits" recorded.

    `cold` is provisional at EVERY cutoff of its season, whether or not it plays
    that week — a cold-start club is low-information by definition and
    `epl.dcfit.ColdStartPosterior` unions it in season-wide. `stale` is never
    flagged, which is the whole finding: 0.001 match-equivalents of evidence and
    the raw-count arm sees a club it knows.
    """
    out = {CUT_A: {"cold"}, CUT_B: {"cold"}, CUT_C: {"cold"}, CUT_D: {"cold"}}
    out.update(override)
    return out


def _world():
    return _corpus(), _archive(), _ledger()


# ==========================================================================
# 0. the pins — §0.1, and the refusals that guard them
# ==========================================================================

def test_the_frozen_constants_are_the_documents(monkeypatch):
    """§2.1, §3.1, §4.1, §4.3: every number the harness may not choose."""
    assert ew.E_STAR == 10.0
    assert ew.E_GRID == (1.0, 3.0, 5.0, 8.0, 12.0)
    assert ew.E_GRID_DEGENERATE == (1.0, 3.0)
    assert ew.WIDENING_ALPHA == 0.5
    assert ew.ADOPT_DELTA == -0.0010
    assert ew.TABLE_TOLERANCE == 0.0002
    assert ew.ARM_NAME == "dc_evwiden"
    assert ew.BASELINE_ARM == "dc_native"
    assert ew.SEED == 20260611
    assert ew.BOOTSTRAP_SEED == 20260814
    assert ew.N_BOOT == 10_000
    assert ew.ALPHA == 0.05
    assert ew.DECAY_HALF_LIFE_DAYS == 365.0
    assert ew.FROZEN_WIDENING == {"mechanism": "c", "strength": 0.5}
    assert ew.SCHEMA_ID == "epl-evwiden-1"
    assert ew.HARNESS_FILES == ("epl/evwiden.py", "epl/tests/test_evwiden.py")


def test_the_pre_stated_counts_are_the_documents():
    """§2.2, §2.3, §3.2, §3.3: the membership, before any fit."""
    assert ew.EXPECTED_THIN == 85
    assert ew.EXPECTED_TREATED == 52
    assert ew.EXPECTED_NEW_CELLS == 51
    assert ew.EXPECTED_NEW_CELLS_PLAYING == 47
    assert ew.EXPECTED_FIT_OPENINGS == 78
    assert ew.EXPECTED_CONTROL_FIXTURES == 820
    assert ew.EXPECTED_PRIMARY_BLOCKS == 62
    assert ew.EXPECTED_CELLS == 4240
    assert ew.EXPECTED_INCUMBENT_FIXTURES == 46
    assert ew.EXPECTED_TABLE_CELLS == 35
    assert ew.EXPECTED_TABLE_TREATED == 16
    assert ew.EXPECTED_TABLE_UNTOUCHED == 19
    assert sum(ew.EXPECTED_THIN_BY_SEASON.values()) == ew.EXPECTED_THIN
    assert (ew.EXPECTED_TABLE_TREATED + ew.EXPECTED_TABLE_UNTOUCHED
            == ew.EXPECTED_TABLE_CELLS)


def test_the_write_set_excludes_everything_the_house_protects():
    """§6 closes the set. A harness that writes `src/` is a harness that broke
    the lock chain, and the lock chain refuses silently."""
    protected = ("src/", "scripts/", "site/", "tools/", "config/", ".github/",
                 "epl/simretro.py", "epl/simmetrics.py",
                 "epl/season/points_adjustments.jsonl",
                 "data/epl/sim/retro_r1.jsonl",
                 "data/epl/fit/walkforward_predictions.parquet",
                 "data/epl/fit/walkforward_ledger.jsonl",
                 "data/epl/matches.parquet")
    for target in ew.WRITES:
        rel = ew.paths.rel(Path(target))
        assert not any(rel.startswith(p) or rel == p for p in protected), rel
    assert ew.paths.rel(ew.EVWIDEN_DIR).startswith("data/epl/fit/evwiden")
    assert ew.paths.rel(ew.TABLE_DIR).startswith("data/epl/sim/evwiden")
    assert ew.paths.rel(ew.EVIDENCE_JSON).startswith("reports/evidence/")


def test_corpus_refuses_a_missing_file(tmp_path):
    with pytest.raises(ew.CorpusMissing):
        ew.load_corpus(tmp_path / "nope.parquet")


def test_corpus_refuses_the_wrong_digest(tmp_path):
    path = tmp_path / "corpus.parquet"
    _corpus().to_parquet(path)
    with pytest.raises(ew.CorpusDigestMismatch):
        ew.load_corpus(path)


def test_corpus_shape_refuses_a_short_corpus():
    """A digest says the bytes changed; the shape check says what about them."""
    with pytest.raises(ew.CorpusShapeMismatch) as exc:
        ew.assert_corpus_shape(_corpus())
    assert "rows" in str(exc.value)


def test_archive_refuses_the_wrong_digest(tmp_path):
    """§0.1: the archive is an INPUT TO THE PREDICATE, not only to the fits."""
    path = tmp_path / "matches.parquet"
    _archive().to_parquet(path)
    with pytest.raises(ew.ArchiveDigestMismatch):
        ew.load_archive(path)


def test_walk_ledger_refuses_the_wrong_digest(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps({"cutoff": CUT_A, "provisional_teams": []}) + "\n")
    with pytest.raises(ew.LedgerDigestMismatch):
        ew.load_walk_ledger(path)


def test_walk_ledger_reads_the_published_provisional_sets(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in [
        {"cutoff": CUT_A, "provisional_teams": ["cold"]},
        {"cutoff": CUT_B, "provisional_teams": []},
    ]) + "\n")
    got = ew.load_walk_ledger(path, require_digest=False)
    assert got == {CUT_A: {"cold"}, CUT_B: set()}


def test_seeded_defect_config_under_mechanism_a_refuses(monkeypatch, tmp_path):
    """§0.2: under mechanism (a) the widening moves into the LIKELIHOOD, the
    posterior stops being arm-invariant, and every pairing claim in §2.3 is
    false. The harness must refuse rather than report a comparison of two
    different posteriors."""
    monkeypatch.setattr(ew, "CONFIG_SHA256", ew.sha256_file(ew.CONFIG_PATH))
    good = {"seed": ew.SEED, "model": {"widening": {"mechanism": "c",
                                                    "strength": 0.5}}}
    assert ew.assert_config_frozen(cfg=good)
    for broken in ({"seed": 1, "model": {"widening": ew.FROZEN_WIDENING}},
                   {"seed": ew.SEED,
                    "model": {"widening": {"mechanism": "a", "strength": 0.5}}},
                   {"seed": ew.SEED,
                    "model": {"widening": {"mechanism": "c", "strength": 0.9}}}):
        with pytest.raises(ew.ConfigNotFrozen):
            ew.assert_config_frozen(cfg=broken)


# ==========================================================================
# 1. effective evidence — §0.3, the fit's own likelihood weight
# ==========================================================================

def test_evidence_is_the_half_life_sum_by_hand():
    """`e(t, C) = SUM 0.5 ** (age_days / 365)`, and nothing else."""
    played = pd.DataFrame([
        {"match_id": "x1", "date": pd.Timestamp("2019-01-06"),
         "home_key": "a", "away_key": "b", "fthg": 1, "ftag": 0, "played": True},
        {"match_id": "x2", "date": pd.Timestamp("2020-01-05"),
         "home_key": "b", "away_key": "c", "fthg": 0, "ftag": 0, "played": True},
    ])
    e = ew.effective_evidence("2020-01-06", played, ["a", "b", "c"])
    assert e["a"] == pytest.approx(0.5 ** (365 / 365))          # exactly one year
    assert e["b"] == pytest.approx(0.5 ** 1 + 0.5 ** (1 / 365))
    assert e["c"] == pytest.approx(0.5 ** (1 / 365))


def test_evidence_is_venue_blind():
    """§0.3: a club accrues evidence home and away alike."""
    home = pd.DataFrame([{"match_id": "h", "date": pd.Timestamp("2020-01-05"),
                          "home_key": "a", "away_key": "z", "fthg": 1,
                          "ftag": 0, "played": True}])
    away = home.copy()
    away[["home_key", "away_key"]] = [["z", "a"]]
    assert (ew.effective_evidence("2020-01-06", home, ["a"])["a"]
            == ew.effective_evidence("2020-01-06", away, ["a"])["a"])


def test_evidence_is_strictly_before_the_cutoff():
    """A match ON the cutoff day contributes nothing: the rule is `date < C`."""
    played = pd.DataFrame([{"match_id": "s", "date": pd.Timestamp("2020-01-06"),
                            "home_key": "a", "away_key": "b", "fthg": 0,
                            "ftag": 0, "played": True}])
    assert ew.effective_evidence("2020-01-06", played, ["a"])["a"] == 0.0


def test_seeded_defect_a_leaky_point_in_time_filter_refuses(monkeypatch):
    """§5.1's `EvidenceLeak`, seeded: replace the `date < C` filter with `<=`.

    This is the defect the guard exists for, and the reason the guard is not
    placed on the filter's own output: re-applying `date < C` to the rows
    `date < C` just selected can never go red. The check is on the AGES that
    weight the sum, so a same-day match — age 0, full weight `0.5 ** 0 = 1` —
    is caught wherever the filter went wrong.
    """
    played = pd.DataFrame([
        {"match_id": "s", "date": pd.Timestamp("2020-01-06"), "home_key": "a",
         "away_key": "b", "fthg": 0, "ftag": 0, "played": True},
        {"match_id": "p", "date": pd.Timestamp("2019-01-06"), "home_key": "a",
         "away_key": "b", "fthg": 0, "ftag": 0, "played": True}])

    # sound filter: the same-day row is excluded and the sum is the old one
    assert ew.effective_evidence("2020-01-06", played, ["a"])["a"] == \
        pytest.approx(0.5)

    def leaky(frame, cutoff):
        dates = pd.to_datetime(frame["date"]).dt.normalize()
        return frame.loc[dates <= pd.Timestamp(cutoff).normalize()]

    monkeypatch.setattr(ew, "prior_rows", leaky)
    with pytest.raises(ew.EvidenceLeak) as exc:
        ew.effective_evidence("2020-01-06", played, ["a"])
    assert "on or after" in str(exc.value)
    # and with the guard off it would silently double the club's evidence
    assert ew.effective_evidence("2020-01-06", played, ["a"],
                                 check_leak=False)["a"] == pytest.approx(1.5)


def test_evidence_drifts_upward_as_a_club_plays():
    """§2.2: the status is as-of-cutoff and a club LEAVES the set as its
    evidence accumulates — the refusal to widen a club forever."""
    played = _archive()
    early = ew.effective_evidence(CUT_A, played, ["rich"])["rich"]
    later = ew.effective_evidence(CUT_C, played, ["rich"])["rich"]
    assert early > later          # nothing new after CUT_A: it only decays
    extra = pd.concat([played, pd.DataFrame([
        {"match_id": "zz", "date": pd.Timestamp(CUT_B) - pd.Timedelta(days=1),
         "home_key": "stale", "away_key": "rich", "fthg": 1, "ftag": 1,
         "played": True}])], ignore_index=True)
    before = ew.effective_evidence(CUT_B, played, ["stale"])["stale"]
    after = ew.effective_evidence(CUT_B, extra, ["stale"])["stale"]
    assert after > before


def test_the_synthetic_world_has_the_evidence_profiles_it_claims():
    """The fixtures are only useful if their `e` values are what they say."""
    corpus, played, _ = _world()
    table = ew.evidence_table(corpus, played)
    at_a = table["2019/20|2020W02"]
    assert at_a["cold"] == 0.0
    assert at_a["stale"] == pytest.approx(0.5 ** 10, rel=1e-9)
    assert 0.0 < at_a["mid"] < ew.E_STAR
    assert at_a["rich"] > ew.E_STAR


# ==========================================================================
# 2. the membership — §2.1's rule, §2.2's cells, §2.3's population
# ==========================================================================

def test_thin_is_the_thinner_side_and_treated_removes_the_already_widened():
    """§1.4 and §2.3: thin is a property of the FIXTURE; treated subtracts the
    fixtures the incumbent predicate already widens."""
    corpus, played, ledger = _world()
    m = ew.membership(corpus, played, ledger, e_star=ew.E_STAR)

    # every fixture with a `stale`, `cold` or `mid` side is thin at e* = 10
    assert set(m.thin) == {"m001", "m002", "m003", "m004", "m006", "m007",
                           "m008"}
    # m005 is rich v rich: the only fixture with no thin side
    assert "m005" not in m.thin
    # m002 (stale v cold), m003 (rich v cold) and m007 (cold v rich) carry a
    # cold-start club, which the incumbent predicate already widens
    assert set(m.already_widened) == {"m002", "m003", "m007"}
    assert set(m.treated) == {"m001", "m004", "m006", "m008"}
    assert len(m.thin) == len(m.treated) + len(m.already_widened)


def test_the_rule_adds_and_never_removes():
    """§2.1's ADD-not-REPLACE ruling: a data-rich incumbent club stays flagged.

    A replacement rule would strip widening from the volatility arm's clubs —
    all data-rich — and make the model MORE confident on the historical corpus,
    the opposite of the motivating direction.
    """
    corpus, played, _ = _world()
    # `rich` is data-rich AND (counterfactually) flagged by the volatility arm
    ledger = _ledger(**{CUT_A: {"cold", "rich"}})
    m = ew.membership(corpus, played, ledger, e_star=ew.E_STAR)
    frame = ew._fixture_frame(corpus, played, ledger)
    at_a = frame.loc[frame["cutoff"] == CUT_A]
    assert bool(at_a.loc[at_a["match_id"] == "m001", "incumbent"].iloc[0])
    # ...so its fixtures are already widened and contribute a zero delta,
    # rather than being stripped of widening by the new rule
    assert "m001" in m.already_widened
    assert "m001" not in m.treated


def test_membership_is_as_of_cutoff_and_a_club_can_leave_the_set():
    """§2.2: recomputed at every cutoff — the refusal to widen a club forever."""
    corpus, played, ledger = _world()
    table = ew.evidence_table(corpus, played)
    # `mid` is thin at e* = 10 at both cutoffs of season one...
    assert table["2019/20|2020W02"]["mid"] < ew.E_STAR
    # ...and a threshold below its own value does not flag it
    tiny = ew.membership(corpus, played, ledger, e_star=1.0)
    assert "m001" not in tiny.thin          # rich v mid: mid's e exceeds 1.0
    assert "m002" in tiny.thin              # stale's e is 0.001


def test_new_cells_are_club_cutoff_pairs_and_playing_is_a_subset():
    """§2.2: 51 cells, of which 47 sit in blocks where the club itself plays."""
    corpus, played, ledger = _world()
    m = ew.membership(corpus, played, ledger, e_star=ew.E_STAR)
    assert set(m.new_cells_playing) <= set(m.new_cells)
    # `stale` is thin and unflagged at CUT_D, a week of its own season in
    # which it does not play: a flagged cell that reaches no fixture
    assert ("2019/20|2020W04", "stale") in m.new_cells
    assert ("2019/20|2020W04", "stale") not in m.new_cells_playing
    # `mid` is thin and unflagged there too, and DOES play, so it reaches one
    assert ("2019/20|2020W04", "mid") in m.new_cells_playing
    # a cold-start club is thin AND flagged, so it is never a NEW cell
    assert not any(club == "cold" for _, club in m.new_cells)


def test_the_grid_is_monotone_and_its_low_points_are_degenerate():
    """§3.1: at e* in {1, 3} every thin fixture is already widened and the delta
    is 0.000000 BY CONSTRUCTION — pre-stated so an identically zero row cannot
    be presented as either a finding or a failure."""
    corpus, played, ledger = _world()
    sizes = {}
    for star in (1.0, 3.0, 5.0, 8.0, 10.0, 12.0):
        m = ew.membership(corpus, played, ledger, e_star=star)
        sizes[star] = (len(m.thin), len(m.treated))
    for a, b in zip(sorted(sizes), sorted(sizes)[1:]):
        assert sizes[a][0] <= sizes[b][0]
        assert sizes[a][1] <= sizes[b][1]
    # the two points §3.1 pre-states as degenerate are named in the module, and
    # the estimand carries the flag on their rows (see the grid test below)
    assert ew.E_GRID_DEGENERATE == (1.0, 3.0)


def test_thin_at_lists_the_grid_points_a_fixture_is_thin_at():
    assert ew.thin_at(0.0) == ["1", "3", "5", "8", "10", "12"]
    assert ew.thin_at(9.0) == ["10", "12"]
    assert ew.thin_at(50.0) == []


def test_membership_digests_do_not_depend_on_iteration_order():
    """§6 step 2 hashes the membership; a reordering must not move a digest."""
    corpus, played, ledger = _world()
    a = ew.membership(corpus, played, ledger)
    b = ew.membership(corpus.iloc[::-1].reset_index(drop=True), played, ledger)
    assert ew.canonical_membership(a) == ew.canonical_membership(b)


def test_seeded_defect_membership_counts_that_moved_refuse():
    """§5.1's `MembershipMismatch`: the counts are pre-stated, so they bind."""
    corpus, played, ledger = _world()
    with pytest.raises(ew.MembershipMismatch) as exc:
        ew.membership_digests(corpus, played, ledger)
    assert "thin fixtures" in str(exc.value)


def test_ledger_must_cover_every_block_opening():
    corpus, played, ledger = _world()
    ew.assert_ledger_covers(corpus, ledger)
    del ledger[CUT_B]
    with pytest.raises(ew.LedgerDigestMismatch):
        ew.assert_ledger_covers(corpus, ledger)


# ==========================================================================
# 3. the schedule and the shards
# ==========================================================================

def test_fit_points_carry_the_whole_block_not_the_thin_subset():
    """§3.2: the identity control is defined over ALL 820 fixtures of the 78
    affected blocks, not over the thin ones."""
    corpus, played, ledger = _world()
    points = ew.fit_points(corpus, [CUT_A], check=False)
    assert len(points) == 1
    assert points[0].match_ids == ("m001", "m002", "m003")
    assert points[0].season == "2019/20"


def test_fit_openings_are_the_grid_union_and_the_primary_is_a_subset():
    """§2.3: 78 openings at the `e* < 12` union, of which the primary's 62 are
    a subset."""
    corpus, played, ledger = _world()
    union = set(ew.fit_openings(corpus, played, ledger))
    primary = set(ew.membership(corpus, played, ledger, e_star=ew.E_STAR).blocks)
    assert primary <= union


def test_shards_are_a_partition():
    corpus, played, ledger = _world()
    points = ew.fit_points(corpus, [CUT_A, CUT_B, CUT_C, CUT_D], check=False)
    parts = [ew.shard_points(points, i, 3) for i in range(3)]
    seen = [p.cutoff for part in parts for p in part]
    assert sorted(seen) == sorted(p.cutoff for p in points)
    assert len(seen) == len(set(seen))


def test_shard_index_out_of_range_refuses():
    corpus, played, ledger = _world()
    points = ew.fit_points(corpus, [CUT_A], check=False)
    for bad in ((3, 3), (-1, 2), (0, 0)):
        with pytest.raises(ew.EvWidenError):
            ew.shard_points(points, *bad)


def test_fit_points_refuse_an_opening_the_corpus_does_not_have():
    corpus, played, ledger = _world()
    with pytest.raises(ew.CorpusShapeMismatch):
        ew.fit_points(corpus, ["1999-01-01"], check=False)


# ==========================================================================
# 4. the stub fit — the ledger machinery, without an ADVI sampler
# ==========================================================================

def _widen(p: np.ndarray) -> list[float]:
    """A stand-in for the incumbent mix: halfway to uniform, at 8 decimals.

    This is NOT `inflate_predictive` and does not pretend to be: the mechanism
    itself is checked against `inflate_predictive` by the direction-canary test,
    on a real grid. What this stands in for is the LEDGER's arithmetic — a
    treated fixture gets a different, deterministic, 8-decimal forecast, which
    is everything the merge, the pairing and the estimand need to be tested on.
    """
    w = 0.5 * np.asarray(p, dtype=float) + 0.5 / 3.0
    out = [round(float(v), 8) for v in w]
    out[-1] = round(1.0 - out[0] - out[1], 8)
    return out


def _stub_fitter(corpus, played, ledger, *, defect: str | None = None):
    """A deterministic fitter with the `Engine.fit` output contract.

    `defect` seeds exactly one §5.1 failure class at a time, which is what §5.3
    asks the adversarial audit to do: each defect alone, on synthetic data.
    """
    evidence = ew.evidence_table(corpus, played)
    by_id = corpus.set_index(corpus["match_id"].astype(str))

    def fit(point, *, grid_treated=(), e_star=ew.E_STAR):
        incumbent = set(ledger[point.cutoff])
        if defect == "predicate":
            incumbent = incumbent | {"rich"}
        thin = {c for c, v in evidence[point.block].items() if v < float(e_star)}
        enlarged = incumbent | thin
        pairs = [(str(by_id.loc[m, "home_key"]), str(by_id.loc[m, "away_key"]))
                 for m in point.match_ids]
        stored = np.array([[float(by_id.loc[m, c]) for c in ew._PROB_COLUMNS]
                           for m in point.match_ids], dtype=float)

        probs_incumbent = stored.copy()
        if defect == "control":
            probs_incumbent[0, 0] += 1e-8

        treated, probs_arm = [], stored.copy()
        for i, (mid, (home, away)) in enumerate(zip(point.match_ids, pairs)):
            if home in incumbent or away in incumbent:
                continue                       # already widened: Arm A is Arm B
            if home in enlarged or away in enlarged:
                treated.append(str(mid))
                probs_arm[i] = _widen(stored[i])
        if defect == "untreated":
            untouched = next(i for i, m in enumerate(point.match_ids)
                             if str(m) not in treated)
            probs_arm[untouched] = _widen(stored[untouched])

        widened = {}
        for mid in point.match_ids:
            if str(mid) in set(grid_treated):
                j = point.match_ids.index(mid)
                widened[str(mid)] = _widen(stored[j])

        health = {"all_finite": True, "sigma_positive": True,
                  "home_adv_sane": True}
        if defect == "health":
            health["sigma_positive"] = False
        out = {
            "cutoff": point.cutoff, "season": point.season, "block": point.block,
            "match_ids": list(point.match_ids), "pairs": pairs,
            "probs_incumbent": probs_incumbent, "probs_arm": probs_arm,
            "probs_widened": widened,
            "provisional_incumbent": sorted(incumbent),
            "provisional_enlarged": sorted(enlarged),
            "provisional_ledger": sorted(ledger[point.cutoff]),
            "treated": sorted(treated),
            "cold_start_teams": ["cold"] if "cold" in incumbent else [],
            "evidence": {c: round(float(v), 8)
                         for c, v in sorted(evidence[point.block].items())},
            "n_training_matches": 100, "n_teams": len(ew_clubs(corpus, point)),
            "anchor_spec": "stub", "latest_training_date": "1999-01-01",
            "warnings": [], "unpriceable": [], "health": health,
            "control_max_abs_diff": 0.0,
            "identity_canary": None if enlarged != incumbent else True,
            "direction_canary": {"PASS": True, "n_fixtures": 1},
            "wall_seconds": 0.01, "fit_seconds": 0.01,
        }
        if defect == "raise":
            raise RuntimeError("the sampler diverged")
        if defect == "unpriceable":
            out["unpriceable"] = [{"match_id": point.match_ids[0]}]
        # the harness's own controls, reproduced here so a stub cannot slip a
        # defect past checks the real Engine performs inline
        if not np.array_equal(probs_incumbent, stored):
            raise ew.ControlMismatch(f"{point.cutoff}: stub control mismatch")
        if sorted(incumbent) != sorted(ledger[point.cutoff]):
            raise ew.PredicateMismatch(f"{point.cutoff}: stub predicate mismatch")
        for i, mid in enumerate(point.match_ids):
            if str(mid) not in treated and \
                    not np.array_equal(probs_arm[i], stored[i]):
                raise ew.UntreatedMoved(f"{point.cutoff}: {mid} moved")
        return out

    return fit


def ew_clubs(corpus, point):
    part = corpus.loc[corpus["block"] == point.block]
    return sorted(set(part["home_key"]) | set(part["away_key"]))


def _run(tmp_path, *, defect=None, points=None, shard="0/1", resume=True,
         world=None):
    corpus, played, ledger = world or _world()
    openings = ew.fit_openings(corpus, played, ledger)
    points = ew.fit_points(corpus, openings, check=False) if points is None \
        else points
    index, count = (int(x) for x in shard.split("/"))
    grid_treated = ew.membership(corpus, played, ledger,
                                 e_star=max(ew.E_GRID)).treated
    return ew.run_fits(ew.shard_points(points, index, count),
                       tmp_path / ew.shard_name(index, count), corpus,
                       fitter=_stub_fitter(corpus, played, ledger, defect=defect),
                       grid_treated=grid_treated, shard_id=shard, resume=resume,
                       verbose=False, harness_frozen=False)


def test_the_stub_run_writes_one_row_per_fixture_of_every_fitted_block():
    """The control is over the WHOLE block, so the ledger is too."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        out = _run(tmp)
        corpus, played, ledger = _world()
        openings = ew.fit_openings(corpus, played, ledger)
        expected = int(corpus["block"].map(ew.block_openings(corpus))
                       .isin(openings).sum())
        assert out["n_rows_written"] == expected
        rows = ew.load_ledger(tmp / ew.shard_name(0, 1))
        assert len(rows) == expected
        assert {r["schema"] for r in rows} == {ew.SCHEMA_ID}


def test_every_row_carries_the_two_level_provenance_contract(tmp_path):
    """§5.2: a field nobody wrote is a field nobody can check afterwards."""
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    for field in ew.REQUIRED_ROW_FIELDS:
        assert field in rows[0], field
    for field in ew.REQUIRED_FIT_FIELDS:
        assert field in rows[0]["fit"], field
    assert rows[0]["arm_a"]["arm"] == ew.ARM_NAME
    assert rows[0]["arm_b"]["arm"] == ew.BASELINE_ARM
    assert rows[0]["arm_b"]["recomputed"] is False
    assert rows[0]["arm_a"]["alpha"] == ew.WIDENING_ALPHA


def test_the_canonical_form_drops_the_volatile_fields(tmp_path):
    """§5.2 fixed the list before any row existed."""
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    text = ew.canonical(rows)
    for field in ew._VOLATILE:
        assert f'"{field}"' not in text, field
    assert '"delta"' in text and '"probs_arm"' in text


def test_a_resumed_run_reproduces_an_uninterrupted_one_byte_for_byte(tmp_path):
    """§5.2: "a resumed run's digest must equal an uninterrupted run's byte for
    byte" — the demand is on the canonical form, not on the raw file."""
    corpus, played, ledger = _world()
    openings = ew.fit_openings(corpus, played, ledger)
    points = ew.fit_points(corpus, openings, check=False)

    whole = tmp_path / "whole"
    whole.mkdir()
    _run(whole, points=points)
    full = ew.run_digest(ew.load_ledger(whole / ew.shard_name(0, 1)))

    part = tmp_path / "part"
    part.mkdir()
    _run(part, points=points[:1])            # interrupted after one fit
    _run(part, points=points)                # resumed
    resumed = ew.load_ledger(part / ew.shard_name(0, 1))
    assert ew.run_digest(resumed) == full
    # ...and the resume did not re-run or duplicate the completed fit
    assert len({(r["key"], r["match_id"]) for r in resumed}) == len(resumed)


def test_a_completed_key_is_skipped_not_refitted(tmp_path):
    corpus, played, ledger = _world()
    points = ew.fit_points(corpus, ew.fit_openings(corpus, played, ledger),
                           check=False)
    _run(tmp_path, points=points)
    again = _run(tmp_path, points=points)
    assert again["n_fits"] == 0
    assert again["n_skipped"] == len(points)
    assert again["n_rows_written"] == 0


# ==========================================================================
# 5. §5.3's seeded defects — each class of §5.1 alone, on synthetic data
# ==========================================================================

def test_seeded_defect_control_mismatch_stops_the_run(tmp_path):
    """§3.2: EXACT equality at the corpus's eight decimals. A 1e-8 perturbation
    is the smallest lie the corpus can be told, and it must still be caught —
    §7 makes widening the tolerance after a mismatch an invalidation."""
    with pytest.raises(ew.ControlMismatch):
        _run(tmp_path, defect="control")


def test_seeded_defect_untreated_moved_stops_the_run(tmp_path):
    """§2.3: "the treatment must touch exactly the fixtures the rule names"."""
    with pytest.raises(ew.UntreatedMoved):
        _run(tmp_path, defect="untreated")


def test_seeded_defect_predicate_mismatch_stops_the_run(tmp_path):
    """§3.2: the control that the incumbent arm being re-keyed IS the incumbent
    arm that published."""
    with pytest.raises(ew.PredicateMismatch):
        _run(tmp_path, defect="predicate")


def test_seeded_defect_unpriceable_fixture_stops_the_run(tmp_path):
    """§2.3 fixes the population and forbids dropping a fixture, so an
    unpriceable one is a defect and never a smaller denominator."""
    with pytest.raises(ew.UnpriceableFixture):
        _run(tmp_path, defect="unpriceable")


def test_seeded_defect_an_arbitrary_exception_becomes_a_typed_fit_failure(tmp_path):
    with pytest.raises(ew.FitFailed) as exc:
        _run(tmp_path, defect="raise")
    assert "the sampler diverged" in str(exc.value)


def test_a_failed_fit_poisons_its_shard_and_the_shard_refuses_to_re_run(tmp_path):
    """§5.1: a failed fit poisons its shard, a failed shard poisons the merge,
    and a partial ledger is never scored."""
    with pytest.raises(ew.FitFailed):
        _run(tmp_path, defect="raise")
    path = tmp_path / ew.shard_name(0, 1)
    poison = ew.poison_rows(path)
    assert poison and poison[0]["error_type"] == "FitFailed"

    # a clean re-run over poison is refused: re-running would leave the poison
    # in place, the merge would refuse anyway, and the fits would be paid twice
    with pytest.raises(ew.ShardFailed) as exc:
        _run(tmp_path)
    assert "poison" in str(exc.value)
    # ...and the merge refuses the same ledger for the same reason
    with pytest.raises(ew.ShardFailed):
        ew.load_ledger(path)


def test_seeded_defect_score_mismatch_in_the_corpus_stops_the_run(tmp_path):
    """§2.3: Arm B's RPS is re-derived from Arm B's own stored probabilities and
    a disagreement past 1e-12 refuses. A corpus whose own columns disagree
    cannot be one arm of a paired comparison."""
    corpus, played, ledger = _world()
    corpus.loc[0, "dc_rps"] = float(corpus.loc[0, "dc_rps"]) + 1e-6
    with pytest.raises(ew.ScoreMismatch):
        ew.check_corpus_scores(corpus)
    with pytest.raises(ew.ScoreMismatch):
        _run(tmp_path, world=(corpus, played, ledger))


def test_seeded_defect_a_row_missing_a_contract_field_refuses(tmp_path):
    _run(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    lines = path.read_text().splitlines()
    broken = json.loads(lines[0])
    broken.pop("delta")
    path.write_text("\n".join([json.dumps(broken)] + lines[1:]) + "\n")
    with pytest.raises(ew.SchemaMismatch) as exc:
        ew.load_ledger(path)
    assert "delta" in str(exc.value)


def test_seeded_defect_a_fit_block_missing_a_contract_field_refuses(tmp_path):
    """§5.2 fixes what a row records at BOTH levels."""
    _run(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    lines = path.read_text().splitlines()
    broken = json.loads(lines[0])
    broken["fit"].pop("archive_sha256")
    path.write_text("\n".join([json.dumps(broken)] + lines[1:]) + "\n")
    with pytest.raises(ew.SchemaMismatch) as exc:
        ew.load_ledger(path)
    assert "archive_sha256" in str(exc.value)


def test_seeded_defect_duplicate_rows_that_disagree_refuse(tmp_path):
    """§5.1's `RowConflict`: append order cannot change a number."""
    _run(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    lines = path.read_text().splitlines()
    twin = json.loads(lines[0])
    with path.open("a") as fh:
        fh.write(json.dumps(twin) + "\n")     # identical: fine
    assert ew.load_ledger(path)
    twin["delta"] = float(twin["delta"]) + 1e-6
    with path.open("a") as fh:
        fh.write(json.dumps(twin) + "\n")     # disagreeing: refused
    with pytest.raises(ew.RowConflict):
        ew.load_ledger(path)


def test_a_torn_tail_is_repaired_and_a_mid_file_tear_is_refused(tmp_path):
    """Only an interrupted append can truncate a ledger, so only the tail may
    be dropped; a malformed line anywhere else is a corrupted file."""
    _run(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    good = path.read_text()

    path.write_text(good + '{"schema": "epl-evwid')
    assert ew.repair_tail(path) > 0
    assert ew.load_ledger(path)

    lines = good.splitlines()
    path.write_text("\n".join([lines[0], "{not json", *lines[1:]]) + "\n")
    with pytest.raises(ew.EvWidenError) as exc:
        ew.read_jsonl(path)
    assert "corrupted rather than partial" in str(exc.value)


def test_an_incomplete_fit_is_not_counted_as_complete(tmp_path):
    """`complete_only`: resume must know an unfinished fit from a finished one
    by the count the ROWS declare, not by the file's length."""
    _run(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    first_key = rows[0]["key"]
    kept = [r for r in rows if r["key"] != first_key][:1] + \
           [r for r in rows if r["key"] == first_key][:1]
    path.write_text("\n".join(json.dumps(r) for r in kept) + "\n")
    # the first fit priced more than one fixture, so one row is a partial fit
    assert first_key not in ew.completed_keys(path)


def test_the_preregistered_directory_is_closed_before_the_freeze(tmp_path):
    """§6 step 3 and §7: an audit run is legitimate and gets its own directory,
    where every row is stamped harness_frozen: false."""
    corpus, played, ledger = _world()
    points = ew.fit_points(corpus, [CUT_A], check=False)
    with pytest.raises(ew.EvWidenError) as exc:
        ew.run_fits(points, ew.EVWIDEN_DIR / "shard_00_of_01.jsonl", corpus,
                    fitter=_stub_fitter(corpus, played, ledger),
                    verbose=False, harness_frozen=False)
    assert "freeze commit" in str(exc.value)
    # the canary record is guarded too: a pre-freeze canary.json left in the run
    # directory is what a later --run reads as "the canary passed"
    with pytest.raises(ew.EvWidenError):
        ew._guard_ledger_location(ew.CANARY_JSON, False)
    # ...and a scratch directory is not
    ew._guard_ledger_location(tmp_path / "shard_00_of_01.jsonl", False)


def test_every_audit_row_is_stamped_unfrozen(tmp_path):
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    assert all(r["harness_frozen"] is False for r in rows)


# ==========================================================================
# 6. the treatment itself — the production path, not a restatement of it
# ==========================================================================

def _poisson_grid(lam_home: float = 1.5, lam_away: float = 1.2,
                  n: int = 11) -> np.ndarray:
    from math import exp, factorial

    h = np.array([exp(-lam_home) * lam_home ** k / factorial(k) for k in range(n)])
    a = np.array([exp(-lam_away) * lam_away ** k / factorial(k) for k in range(n)])
    g = np.outer(h, a)
    return g / g.sum()


class _FakePosterior:
    """The smallest object the production widening path will accept.

    It carries a real normalised scoreline grid and delegates to `draw_api`'s
    own `finalize_grid`, so a test that goes through it is testing the shipped
    mechanism rather than a re-implementation of it.
    """

    def __init__(self, grid=None, mechanism: str = "c", strength: float = 0.5):
        self._grid = _poisson_grid() if grid is None else grid
        self.provisional_teams: set[str] = set()
        self._cfg = {"widening": {"mechanism": mechanism, "strength": strength}}
        self.teams = ["a", "b"]
        self._idx = {"a": 0, "b": 1}
        self.likelihood = "dixon_coles"

    def predict_scoreline(self, home, away, neutral=False):
        from wcmodel.model.draw_api import finalize_grid

        provisional = (home in self.provisional_teams
                       or away in self.provisional_teams)
        return finalize_grid(self._grid.copy(), self, provisional=provisional)

    def predict_1x2(self, home, away, neutral=False):
        from wcmodel.model.draw_api import grid_one_x_two

        return grid_one_x_two(self.predict_scoreline(home, away, neutral))


def test_provisional_as_is_the_whole_treatment_and_it_restores():
    """§2.1: re-keying is "put a different set on the posterior and ask again"."""
    post = _FakePosterior()
    post.provisional_teams = {"z"}
    with ew.provisional_as(post, ["a"]):
        assert post.provisional_teams == {"a"}
    assert post.provisional_teams == {"z"}

    with pytest.raises(RuntimeError):
        with ew.provisional_as(post, ["a"]):
            raise RuntimeError("boom")
    assert post.provisional_teams == {"z"}    # restored on the way out, too


def test_the_treated_fixture_gets_a_different_forecast_and_the_base_one_does_not():
    post = _FakePosterior()
    with ew.provisional_as(post, ()):
        base = ew.predict_rows(post, [("a", "b")])
    with ew.provisional_as(post, ("a",)):
        wide = ew.predict_rows(post, [("a", "b")])
    assert not np.array_equal(base, wide)
    # ...and widening does not care WHICH side carried the flag
    with ew.provisional_as(post, ("b",)):
        other = ew.predict_rows(post, [("a", "b")])
    assert np.array_equal(wide, other)


def test_direction_canary_holds_the_mix_to_inflate_predictive_itself():
    """§5.3: "Every treated grid must equal `inflate_predictive(base_grid,
    is_provisional=True, strength=0.5)` exactly, and carry strictly higher
    entropy than its base — the mechanism's own guarantee, checked rather than
    assumed"."""
    post = _FakePosterior()
    out = ew.direction_canary(post, [("a", "b")])
    assert out["PASS"] is True
    assert out["max_abs_grid_diff"] == 0.0
    assert out["min_entropy_gain"] > 0.0
    assert out["alpha"] == ew.WIDENING_ALPHA


def test_seeded_defect_a_widening_that_does_not_widen_fails_the_direction_canary():
    """Under mechanism (a) `finalize_grid` applies no predict-time mix, so the
    "widened" grid is the base grid: same numbers, zero entropy gain."""
    post = _FakePosterior(mechanism="a")
    with pytest.raises(ew.CanaryFailed) as exc:
        ew.direction_canary(post, [("a", "b")])
    assert "entropy" in str(exc.value)


def test_seeded_defect_a_mix_at_the_wrong_strength_fails_the_direction_canary():
    """§2.1 freezes alpha at 0.5. A grid mixed at another strength is a
    different treatment from the preregistered one."""
    post = _FakePosterior(strength=0.25)
    with pytest.raises(ew.CanaryFailed) as exc:
        ew.direction_canary(post, [("a", "b")], strength=ew.WIDENING_ALPHA)
    assert "inflate_predictive" in str(exc.value)


def test_predict_rows_refuses_a_club_the_posterior_cannot_price():
    post = _FakePosterior()
    with pytest.raises(ew.UnpriceableFixture):
        ew.predict_rows(post, [("a", "ghost")])


def test_grid_entropy_is_the_shannon_entropy_of_the_pmf():
    flat = np.full((2, 2), 0.25)
    assert ew.grid_entropy(flat) == pytest.approx(np.log(4))
    point = np.zeros((2, 2))
    point[0, 0] = 1.0
    assert ew.grid_entropy(point) == pytest.approx(0.0)


# ==========================================================================
# 7. the evidence canary — §5.3's two legs, and its positive control
# ==========================================================================

def test_evidence_canary_passes_on_a_sound_frame():
    played = _archive()
    clubs = list(CLUBS)
    out = ew.evidence_canary(played, CUT_B, clubs)
    assert out["PASS"] is True
    assert out["negative_leg_max_abs_diff"] == 0.0
    assert out["positive_control_max_abs_diff"] > 1e-9
    assert out["provisional_checked"] is False


def test_the_evidence_canary_corrupts_clubs_and_not_only_scores():
    """`e` never reads a score, so a score-only corruption would pass on a
    BROKEN filter. Reassigning the clubs is what makes the negative leg able
    to fail."""
    played = _archive()
    after = ew.corrupt_archive(played, CUT_B, side="after")
    late = after.loc[pd.to_datetime(after["date"]) >= pd.Timestamp(CUT_B)]
    assert len(late)
    assert set(late["home_key"]) == {ew._CANARY_CLUB}
    assert set(late["away_key"]) == {ew._CANARY_CLUB}


def test_seeded_defect_a_leak_the_per_call_guard_cannot_see_fails_the_canary(
        monkeypatch):
    """The canary's independent value, in one test.

    `effective_evidence`'s own guard catches a filter that admits a same-day or
    later row, because such a row weights at `0.5 ** 0` or more. It CANNOT catch
    a sum that folds the future in at a plausible-looking weight — the `abs(age)`
    bug below, which reads a match six months AFTER the cutoff as if it were six
    months before. Every age stays positive, every weight stays in (0, 1], and
    nothing local looks wrong. The canary catches it anyway, because corrupting
    the post-cutoff rows moves a number that must not move.
    """
    played = _archive()

    def folded(cutoff, frame, clubs=None, **kwargs):
        ts = pd.Timestamp(cutoff).normalize()
        dates = pd.to_datetime(frame["date"]).dt.normalize()
        age = np.abs((ts - dates).dt.days.to_numpy(float))     # the defect
        weight = 0.5 ** (age / 365.0)
        out = {str(c): 0.0 for c in (clubs or ())}
        for column in ("home_key", "away_key"):
            for club, w in zip(frame[column].astype(str), weight):
                if club in out:
                    out[club] += float(w)
        return out

    monkeypatch.setattr(ew, "effective_evidence", folded)
    with pytest.raises(ew.EvidenceCanaryFailed) as exc:
        ew.evidence_canary(played, CUT_A, list(CLUBS))
    assert "negative leg" in str(exc.value)


def test_seeded_defect_a_canary_with_nothing_to_corrupt_refuses():
    """"A canary that cannot fail is not a canary" — including one whose
    corruption mask happened to be empty."""
    played = _archive()
    with pytest.raises(ew.EvWidenError) as exc:
        ew.corrupt_archive(played, "1900-01-01", side="before")
    assert "nothing to corrupt" in str(exc.value)


def test_the_evidence_canary_checks_both_provisional_sets_when_it_can():
    """§5.3 demands "every `e(t, C)` and BOTH provisional sets bit-identical"."""
    played = _archive()
    calls = []

    def provisional_fn(frame):
        calls.append(len(frame))
        return {"cold"}

    out = ew.evidence_canary(played, CUT_B, list(CLUBS),
                             provisional_fn=provisional_fn)
    assert out["provisional_sets_identical"] is True
    assert out["provisional_checked"] is True
    assert len(calls) == 2                       # sound frame and corrupt one


def test_seeded_defect_a_provisional_set_that_moves_fails_the_canary():
    played = _archive()
    seen = {"n": 0}

    def provisional_fn(frame):
        seen["n"] += 1
        return {"cold"} if seen["n"] == 1 else {"cold", "rich"}

    with pytest.raises(ew.EvidenceCanaryFailed):
        ew.evidence_canary(played, CUT_B, list(CLUBS),
                           provisional_fn=provisional_fn)


def test_identity_canary_demands_byte_equality_at_a_threshold_that_adds_nobody():
    """§5.3: "An `e*` low enough to add nobody must yield `np.array_equal` with
    the corpus rows"."""
    corpus, played, ledger = _world()
    point = ew.fit_points(corpus, [CUT_A], check=False)[0]
    fitter = _stub_fitter(corpus, played, ledger)
    out = ew.identity_canary(fitter, point, corpus, e_star=0.0)
    assert out["PASS"] is True
    assert out["clubs_added"] == []
    assert out["max_abs_diff"] == 0.0


def test_seeded_defect_identity_canary_catches_a_treatment_that_adds_something():
    """At the primary threshold the union DOES add a club, so the canary must
    refuse — which is what makes its pass at `e* = 0` mean something."""
    corpus, played, ledger = _world()
    point = ew.fit_points(corpus, [CUT_A], check=False)[0]
    fitter = _stub_fitter(corpus, played, ledger)
    with pytest.raises(ew.CanaryFailed):
        ew.identity_canary(fitter, point, corpus, e_star=ew.E_STAR)


# ==========================================================================
# 8. the estimand — §2.3, against arithmetic computed here rather than there
# ==========================================================================

def _merged(tmp_path):
    _run(tmp_path)
    return ew.load_ledger(tmp_path / ew.shard_name(0, 1))


def _hand_deltas(rows, e_star=ew.E_STAR):
    """The paired deltas, recomputed from the ROWS' own probabilities."""
    out = {}
    for r in rows:
        if float(r["e_min"]) >= e_star:
            continue
        y = int(r["y"])
        a = float(score_mod.rps(np.array([r["probs_arm"]]), np.array([y]))[0])
        b = float(score_mod.rps(np.array([r["probs_native"]]), np.array([y]))[0])
        out[r["match_id"]] = a - b
    return out


def test_the_estimand_is_the_mean_paired_delta_over_the_thin_population(tmp_path):
    rows = _merged(tmp_path)
    hand = _hand_deltas(rows)
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    assert result["n"] == len(hand) == 7
    assert result["mean"] == pytest.approx(float(np.mean(list(hand.values()))))
    assert result["estimand"].startswith("mean paired RPS delta, dc_evwiden "
                                         "minus dc_native")


def test_the_already_widened_fixtures_carry_a_delta_of_exactly_zero(tmp_path):
    """§2.3 states the dilution up front: 33 of the 85 are structural zeros, so
    the estimand's sign equals the treated subset's by arithmetic."""
    rows = _merged(tmp_path)
    thin = [r for r in rows if float(r["e_min"]) < ew.E_STAR]
    already = [r for r in thin if r["incumbent_widened"]]
    assert already
    assert all(float(r["delta"]) == 0.0 for r in already)
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    treated = result["secondaries"]["treated_subset"]
    assert treated["n"] == len(thin) - len(already)
    assert np.sign(result["mean"]) == np.sign(treated["mean"])
    assert result["mean"] == pytest.approx(
        treated["mean"] * treated["n"] / result["n"])


def test_the_full_population_secondary_is_an_arithmetic_identity(tmp_path):
    """§2.3: "Under ADD this is the estimand x 85/2280 AS AN ARITHMETIC
    IDENTITY (untreated deltas are exactly zero), printed as context, never a
    gate"."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, n_boot=200, corpus_rows=2280)
    full = result["secondaries"]["full_population"]
    assert full["mean"] == pytest.approx(result["mean"] * result["n"] / 2280)
    assert full["decides"] == "nothing"


def test_both_intervals_are_reported_and_they_use_different_blocks(tmp_path):
    """§2.3 requires both and §4.1 gates on both: the season interval's job is
    to refuse a result carried by one season."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, n_boot=500, corpus_rows=len(rows))
    assert len(result["ci95"]) == 2 and len(result["ci95_season"]) == 2
    assert result["bootstrap"]["primary_blocks"] == "season|ISO week"
    assert result["bootstrap"]["secondary_blocks"] == "season"
    assert result["bootstrap"]["seed"] == ew.BOOTSTRAP_SEED
    thin = [r for r in rows if float(r["e_min"]) < ew.E_STAR]
    assert result["n_blocks"] == len({r["block"] for r in thin})
    assert result["n_season_blocks"] == len({r["season"] for r in thin})


def test_the_primary_interval_reproduces_the_projects_own_bootstrap(tmp_path):
    """The CI is `epl.score.block_bootstrap_ci` at the pre-stated seed, not a
    second implementation of a percentile bootstrap."""
    rows = _merged(tmp_path)
    thin = [r for r in rows if float(r["e_min"]) < ew.E_STAR]
    lo, hi, n = score_mod.block_bootstrap_ci(
        np.array([float(r["delta"]) for r in thin]),
        [str(r["block"]) for r in thin], n_boot=500, alpha=ew.ALPHA,
        seed=ew.BOOTSTRAP_SEED)
    result = ew.estimand(rows, n_boot=500, corpus_rows=len(rows))
    assert result["ci95"] == [lo, hi]
    assert result["n_blocks"] == n


def test_the_grid_is_assembled_from_the_same_fits_and_agrees_at_the_primary(
        tmp_path):
    """§3.1: "each point's thin-population mean delta, treated count, and
    week-block CI, FROM THE SAME 78 FITS"."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    grid = {g["e_star"]: g for g in result["secondaries"]["grid"]}
    assert set(grid) == {1.0, 3.0, 5.0, 8.0, 10.0, 12.0}
    assert grid[ew.E_STAR]["mean"] == pytest.approx(result["mean"])
    assert grid[ew.E_STAR]["population"] == result["n"]
    for a, b in zip(sorted(grid), sorted(grid)[1:]):
        assert grid[a]["population"] <= grid[b]["population"]
    for star in ew.E_GRID_DEGENERATE:
        assert grid[star]["degenerate_by_construction"] is True


def test_seeded_defect_a_grid_row_with_no_widened_value_refuses(tmp_path):
    """A pass-3 value the run never computed cannot be quietly skipped: the
    grid claims to come from the same fits, and a hole means it does not."""
    rows = _merged(tmp_path)
    for r in rows:
        r["probs_widened"] = None
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.estimand(rows, n_boot=50, corpus_rows=len(rows))
    assert "widened probabilities" in str(exc.value)


def test_seeded_defect_an_untreated_fixture_with_a_delta_refuses(tmp_path):
    """The full-population identity would be FALSE if an untreated fixture
    carried a delta, so the harness refuses instead of printing it."""
    rows = _merged(tmp_path)
    stray = next(r for r in rows if float(r["e_min"]) >= ew.E_STAR)
    stray["delta"] = 1e-9
    with pytest.raises(ew.UntreatedMoved):
        ew.estimand(rows, n_boot=50, corpus_rows=len(rows))


def test_seeded_defect_a_population_that_is_not_the_pre_stated_one_refuses(
        tmp_path):
    """§2.3 fixes the population and forbids dropping a fixture for any reason."""
    rows = _merged(tmp_path)
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.estimand(rows, n_boot=50, corpus_rows=len(rows), expected_thin=85)
    assert "not the pre-stated 85" in str(exc.value)


def test_the_strata_read_the_category_off_the_models_own_cold_start_verdict(
        tmp_path):
    """§3.1's two categories: returning-thin vs cold-start tail, decided by
    `epl.dcfit.cold_start_clubs`'s own verdict recorded on the fit row, not by
    a list of club names typed into the harness."""
    rows = _merged(tmp_path)
    cold = ew.cold_start_club_seasons(rows)
    assert ("2019/20", "cold") in cold
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    labels = {s["stratum"] for s in result["secondaries"]["strata"]["category"]}
    assert labels <= set(ew.STRATA_CATEGORIES)
    total = sum(s["n"] for s in result["secondaries"]["strata"]["category"])
    assert total == result["n"]
    seasons = sum(s["n"] for s in result["secondaries"]["strata"]["season"])
    assert seasons == result["n"]


def test_the_thin_side_is_the_smaller_e_side():
    assert ew.thin_side({"home_key": "a", "away_key": "b",
                         "e_home": 1.0, "e_away": 9.0}) == "a"
    assert ew.thin_side({"home_key": "a", "away_key": "b",
                         "e_home": 9.0, "e_away": 1.0}) == "b"
    assert ew.thin_side({"home_key": "a", "away_key": "b",
                         "e_home": 5.0, "e_away": 5.0}) == "a"   # ties are fixed


def test_the_movement_diagnostic_prints_beside_the_reseed_scale(tmp_path):
    """§3.1: so "did the treatment move more than re-seeding does" is on the
    record whichever way the estimand lands."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    movement = result["secondaries"]["movement"]
    assert movement["max_abs_prob_shift"] > 0
    assert movement["reseed_scale"]["pooled_shift"] == 0.000075
    assert movement["reseed_scale"]["source"] == "reports/epl_walkforward.md"


def test_power_is_reported_and_decides_nothing(tmp_path):
    """§2.3: "No power claim is made in advance… no threshold in §4 moves in
    response"."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    power = result["power"]
    assert power["mde_80pct_two_sided_5pct"] == pytest.approx(
        power["multiplier"] * power["se_iid"])
    assert "no power claim" in power["note"]
    assert result["decides"].startswith("nothing")
    assert result["secondaries_decide"] == "nothing"


def test_a_population_of_structural_zeros_is_degenerate_not_a_finding():
    """§3.1 pre-states the identically zero row so it cannot be presented as
    either a finding or a failure."""
    out = ew._summarise(np.zeros(5), list("aabbc"), n_boot=100, seed=1)
    assert out["mean"] == 0.0 and out["ci95"] == [0.0, 0.0]
    assert out["degenerate"] is True


# ==========================================================================
# 9. the adoption rule — §4.1, all four, none sufficient
# ==========================================================================

_PASSING_TABLE = {"PASS": True, "pooled_delta_trps": 0.0}


def test_adoption_needs_all_four_conditions():
    """§4.1: "All four are required and none is sufficient"."""
    good = ew.adoption(-0.002, [-0.003, -0.001], [-0.004, -0.0005],
                       _PASSING_TABLE)
    assert good["verdict"] == "ADOPT"

    cases = [
        # a point estimate that misses the bar, both intervals clean
        (-0.0009, [-0.002, -0.0001], [-0.002, -0.0001], _PASSING_TABLE),
        # the bar met, the week-block interval straddling zero
        (-0.002, [-0.004, 0.0001], [-0.004, -0.001], _PASSING_TABLE),
        # the bar met, both weeks clean, the SEASON interval straddling zero
        (-0.002, [-0.004, -0.001], [-0.005, 0.0002], _PASSING_TABLE),
        # everything at match level, and the table gate failing
        (-0.002, [-0.004, -0.001], [-0.005, -0.0005],
         {"PASS": False, "pooled_delta_trps": 0.01}),
    ]
    for delta, block, season, table in cases:
        assert ew.adoption(delta, block, season, table)["verdict"] == \
            "DC_NATIVE STANDS"


def test_adoption_is_incomplete_without_a_table_leg():
    """§4.1 makes all four necessary, so a match-level result with no table leg
    behind it cannot adopt — and an absent gate is not a passed one."""
    out = ew.adoption(-0.002, [-0.003, -0.001], [-0.004, -0.0005], None)
    assert out["verdict"].startswith("INCOMPLETE")
    assert out["conditions"]["iv_table_gate"]["PASS"] is None


def test_the_adoption_bar_is_the_house_model_change_bar():
    """§4.2: the full bar applies, on the preregistered population — not
    freshness's operational -0.00030."""
    assert ew.adoption(-0.0010, [-0.002, -0.0001], [-0.002, -0.0001],
                       _PASSING_TABLE)["verdict"] == "ADOPT"
    assert ew.adoption(-0.00099, [-0.002, -0.0001], [-0.002, -0.0001],
                       _PASSING_TABLE)["verdict"] == "DC_NATIVE STANDS"


def test_adoption_is_applied_by_nobody():
    """§4.5: "No script, agent or report may change any arm on the strength of
    these numbers"."""
    out = ew.adoption(-0.002, [-0.003, -0.001], [-0.004, -0.0005],
                      _PASSING_TABLE)
    assert out["applied_by"].startswith("nobody")
    assert "epl_sim_amendments.md" in out["applied_by"]


# ==========================================================================
# 10. the merge — pairing discipline, and the ways a partial run scores anyway
# ==========================================================================

def _merge(tmp_path, **kwargs):
    corpus, played, ledger = kwargs.pop("world", None) or _world()
    openings = ew.fit_openings(corpus, played, ledger)
    defaults = dict(shards=1, directory=tmp_path, corpus=corpus, played=played,
                    ledger=ledger, write=False, expected=openings,
                    harness_frozen=True, n_boot=200, require_canaries=False)
    defaults.update(kwargs)
    return ew.merge(**defaults)


def test_the_merge_scores_a_complete_run(tmp_path):
    _run(tmp_path)
    _freeze_rows(tmp_path)
    out = _merge(tmp_path)
    assert out["n_fits"] == 4
    assert out["n_fixtures"] == 8
    assert out["adoption"]["verdict"].startswith("INCOMPLETE")   # no table leg
    assert out["identity_control"]["max_abs_diff"] == 0.0
    assert out["config"]["widening"] == ew.FROZEN_WIDENING


def test_the_merge_refuses_an_unfrozen_harness(tmp_path):
    """§7: a run that precedes the §6 freeze commit is not this experiment."""
    _run(tmp_path)
    with pytest.raises(ew.EvWidenError) as exc:
        _merge(tmp_path, harness_frozen=False)
    assert "freeze" in str(exc.value)


def test_the_merge_refuses_rows_stamped_unfrozen(tmp_path):
    """The freeze is a property of the ROW, not of the merge's clock — the
    predecessors' back-dating guard, kept."""
    _run(tmp_path)                       # every row carries harness_frozen: false
    with pytest.raises(ew.EvWidenError) as exc:
        _merge(tmp_path)
    assert "back-dating" in str(exc.value)


def _freeze_rows(tmp_path, shards=1):
    """Re-stamp an audit ledger as frozen — for tests of what comes AFTER the
    freeze, and never a thing the harness itself will do."""
    for i in range(shards):
        path = tmp_path / ew.shard_name(i, shards)
        if not path.exists():
            continue
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        for r in rows:
            r["harness_frozen"] = True
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_the_merge_refuses_a_missing_shard(tmp_path):
    _run(tmp_path, shard="0/2")
    _freeze_rows(tmp_path, 2)
    with pytest.raises(ew.ShardFailed) as exc:
        _merge(tmp_path, shards=2)
    assert "never finished" in str(exc.value)


def test_the_merge_refuses_a_short_shard(tmp_path):
    """§5.1: not a superset, not a subset."""
    corpus, played, ledger = _world()
    points = ew.fit_points(corpus, ew.fit_openings(corpus, played, ledger),
                           check=False)
    _run(tmp_path, points=points[:2])
    _freeze_rows(tmp_path)
    with pytest.raises(ew.MergeIncomplete) as exc:
        _merge(tmp_path)
    assert "missing" in str(exc.value)


def test_the_merge_refuses_a_poisoned_shard(tmp_path):
    _run(tmp_path)
    _freeze_rows(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    with path.open("a") as fh:
        fh.write(json.dumps({"poison": True, "key": "k", "cutoff": CUT_A,
                             "error_type": "FitFailed", "error": "x"}) + "\n")
    with pytest.raises(ew.ShardFailed):
        _merge(tmp_path)


def test_the_merge_refuses_a_row_outside_its_own_partition(tmp_path):
    """The shards are a partition and a row in two of them is a fixture counted
    twice."""
    _run(tmp_path, shard="0/2")
    _run(tmp_path, shard="1/2")
    _freeze_rows(tmp_path, 2)
    a, b = (tmp_path / ew.shard_name(i, 2) for i in range(2))
    # a WHOLE fit from the other shard: one row of it would read as a partial
    # fit and be dropped, and the point is a fixture counted twice
    other = [json.loads(l) for l in b.read_text().splitlines() if l.strip()]
    key = other[0]["key"]
    with a.open("a") as fh:
        for row in other:
            if row["key"] == key:
                fh.write(json.dumps(row) + "\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        _merge(tmp_path, shards=2)
    assert "outside its own partition" in str(exc.value)


def test_two_shards_merge_to_the_same_numbers_as_one(tmp_path):
    """A partition is only a partition if it does not change the answer."""
    whole, split = tmp_path / "whole", tmp_path / "split"
    whole.mkdir(), split.mkdir()
    _run(whole)
    _freeze_rows(whole)
    one = _merge(whole)
    for i in range(2):
        _run(split, shard=f"{i}/2")
    _freeze_rows(split, 2)
    two = _merge(split, shards=2)
    assert one["mean"] == two["mean"]
    assert one["n_fixtures"] == two["n_fixtures"]
    assert one["run_digest"] == two["run_digest"]


def test_seeded_defect_a_substituted_fixture_refuses(tmp_path):
    """The rejoin discipline: a row that pairs by id but describes a DIFFERENT
    fixture would pair Arm A against somebody else's Arm B."""
    _run(tmp_path)
    _freeze_rows(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows[0]["home_key"] = "somebody_else"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        _merge(tmp_path)
    assert "substitution" in str(exc.value)


def test_seeded_defect_a_recomputed_arm_b_refuses(tmp_path):
    """§2.3: Arm B is NOT recomputed. A row carrying different numbers under its
    name has recomputed it, which is a different experiment."""
    _run(tmp_path)
    _freeze_rows(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows[0]["probs_native"] = [0.4, 0.3, 0.3]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        _merge(tmp_path)
    assert "recomputed" in str(exc.value)


def test_seeded_defect_a_row_for_a_fixture_the_corpus_does_not_have_refuses(
        tmp_path):
    _run(tmp_path)
    _freeze_rows(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows[0]["match_id"] = "ghost"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        _merge(tmp_path)
    assert "does not" in str(exc.value)


def test_seeded_defect_arm_bs_rps_is_recomputed_at_the_merge(tmp_path):
    """§2.3: "The harness recomputes Arm B's RPS from stored probabilities and
    refuses at > 1e-12 disagreement"."""
    _run(tmp_path)
    _freeze_rows(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows[0]["rps_native"] = float(rows[0]["rps_native"]) + 1e-9
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ew.ScoreMismatch):
        _merge(tmp_path)


def test_the_merge_refuses_without_a_passing_canary_record(tmp_path):
    """§5.3 and RUN_ORDER: the preconditions gate the NUMBER, not the wall
    clock, so they are re-read at the merge from the records beside the shards."""
    _run(tmp_path)
    _freeze_rows(tmp_path)
    with pytest.raises(ew.CanaryFailed) as exc:
        _merge(tmp_path, require_canaries=True)
    assert "precondition" in str(exc.value)

    ew.write_canaries({"PASS": False, "evidence": {"PASS": False}},
                      tmp_path / ew.CANARY_NAME)
    with pytest.raises(ew.CanaryFailed):
        _merge(tmp_path, require_canaries=True)

    ew.write_canaries({"PASS": True, "evidence": {"PASS": True}},
                      tmp_path / ew.CANARY_NAME)
    assert _merge(tmp_path, require_canaries=True)["n_fixtures"] == 8
