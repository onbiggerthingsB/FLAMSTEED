"""The evidence-mass widening harness, held to the preregistration that precedes it.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_evwiden.py -q

`reports/epl_widening_prereg_v3.md` is the SOLE LAW. v1 was invalidated under
v1's own R-B6; v2 was defeated by the one pass it authorised for exactly
that purpose — v2 §8.2 pass 7 ran on 2026-08-28 and measured three of its thirty-five
mandatory parity cells as unpriceable — so v2 was closed and v3 carries its law
against the census that pass produced (§0.6: 32 cells, 15 treated, 17 untouched,
MW6 still 7 of 7 and still the only all-treated label). Both are lineage and
decide nothing. v3 fixes the rule, its one frozen constant, the estimand, both
intervals, §4.1's FOUR-condition adoption rule — the two match intervals, §5's
table gate and §5.4's unanimity rule — the refusal semantics and the scope
BEFORE this harness existed. These tests hold `epl.evwiden` to that document,
and they are shaped around the six ways this particular experiment could produce
a number nobody should believe:

* **A treatment that is not the treatment.** The whole design rests on §0.2:
  mechanism (c) is a predict-time mix, the fitted posterior is arm-invariant, and
  a treated fixture receives EXACTLY the one incumbent mix at alpha = 0.5. The
  direction canary checks that against `wcmodel.model.widening.inflate_predictive`
  itself, on a real grid, rather than against a restatement of it.
* **A population that moved.** 85 thin fixtures, 52 treated, 51 cells, 78
  openings, 32 table cells of which 15 are treated and 17 untouched — every one
  of them pre-stated. The membership tests
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

§8.5'S EIGHTEEN CONFORMANCE ROWS ARE COMMITTED TESTS HERE, one per row, with
stable ids `test_conformance_L1` … `test_conformance_L18`. The pytest SESSION
writes what they did to `data/epl/fit/evwiden_conformance.json`, and
`--freeze-block` reads that artifact rather than any report this module or the
harness computed: "the report may not be its own witness" (§8.5). A row is green
iff its own test id is present and passed there.

§5.3'S SEEDED DEFECTS RUN HERE AND ONLY HERE. "The adversarial audit seeds each
defect class of §5.1 alone and demands red under the harness's own tests — **on
synthetic corpora only**." Each `test_seeded_*` below is one defect class, alone.

THE AUTOUSE ISOLATION FIXTURE IS FUNCTION-SCOPED, and §8.9 says so in those
words: it snapshots §8.8's preregistered paths around **every test in this
module** and fails the test that moved one. It does not speak for import-time,
collection-time, session-fixture, subprocess or crash-time writes.
"""
from __future__ import annotations

import json
import subprocess
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

#: The preregistration this harness implements. v3 is the SOLE LAW; v2 and v1
#: are lineage and decide nothing (§8.1).
PREREG = Path("reports/epl_widening_prereg_v3.md")
PREREG_V1 = Path("reports/epl_widening_prereg.md")

#: The `@pinned` tests of §7.4: they read the pinned artifacts DELIBERATELY, to
#: re-derive the document's own census. They fit nothing and simulate nothing,
#: they are authorised by name under §8.2, and they are not covered by §7.4's
#: SYNTHETIC definition.
pinned = pytest.mark.skipif(
    not (PINNED_CORPUS.exists() and PINNED_ARCHIVE.exists()
         and PINNED_LEDGER.exists()),
    reason="the pinned corpus, archive and walk-forward ledger are on the "
           "machine that ran the walk and nowhere else")


#: §8.8's attestation names the directories that must stay empty until §8.4
#: step 1 runs, and the harness's own guards are keyed to them.
PREREGISTERED_TREE = (ew.EVWIDEN_DIR, ew.TABLE_DIR, ew.SEQUENCE_DIR,
                      ew.FIRST_FIT_JSON, ew.FIRST_FIT_WITNESS,
                      ew.EVWIDEN_JSON, ew.FEASIBILITY_RECORD)


def _preregistered_tree_state():
    """What §8.8's attestation covers, as a comparable snapshot."""
    state = {}
    for target in PREREGISTERED_TREE:
        if target.is_dir():
            state[str(target)] = sorted(
                (str(p.relative_to(target)), p.stat().st_size,
                 p.stat().st_mtime_ns)
                for p in target.rglob("*") if p.is_file())
        elif target.exists():
            state[str(target)] = (target.stat().st_size,
                                  target.stat().st_mtime_ns)
        else:
            state[str(target)] = None
    return state


@pytest.fixture(autouse=True)
def _the_preregistered_directories_stay_untouched():
    """§8.8, made a property of the SUITE rather than of each test's care.

    A first-fit record was found in `data/epl/fit/evwiden/` while §8.8's
    attestation said no such file could exist. It was not a fit: at `6bbacd0`
    the record's writer still took a directory argument defaulting to the
    preregistered run directory, and a working-tree version of that commit's own
    test called it without a `tmp_path`, so a test wrote into the real
    directory. §8.9 records the event, the deletion and the reasoning.

    This fixture is the hole closed as far as a function-scoped fixture can
    close it. Every test in this module runs inside it, and a test that creates,
    changes or removes anything under `data/epl/fit/evwiden*`,
    `data/epl/sim/evwiden*` or the sequence directory fails AT THE TEST rather
    than being found later by an audit. It cannot see a write made at import
    time, at collection time, by a session fixture, by a subprocess or by a
    process that dies mid-test, and §8.9 does not claim it can. The tests that
    legitimately touch these paths do it by pointing the module's own constants
    at a `tmp_path`, which is what they were already doing — this makes the ones
    that forget impossible to miss.
    """
    before = _preregistered_tree_state()
    yield
    after = _preregistered_tree_state()
    moved = [k for k in before if before[k] != after[k]]
    assert not moved, (
        "a test touched the preregistered run tree: "
        + "; ".join(f"{k}: {before[k]!r} -> {after[k]!r}" for k in moved)
        + ". §8.8 attests that nothing exists under data/epl/fit/evwiden* or "
          "data/epl/sim/evwiden* before §8.4 step 1, and a test that writes "
          "there makes that attestation false. Point the module's constants at "
          "a tmp_path instead.")


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

#: §7.4's corrected inventory of fact. There are THREE generators — `_archive`,
#: `_corpus` and `_ledger`, with `_world` returning the three together — and
#: FIVE invented club names, not four: `other` appears in `_archive()` as the
#: counterparty club and is not in `CLUBS`, which is why v1 missed it.
#: §7.4 makes the ancestry claim a test rather than an assertion:
#: `test_the_synthetic_clubs_are_absent_from_the_pinned_artifacts` below.
SYNTHETIC_CLUBS = ("rich", "mid", "stale", "cold", "other")
SYNTHETIC_GENERATORS = ("_archive", "_corpus", "_ledger")


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
# §7.4 — "synthetic" has an enforceable definition, and it is enforced HERE
# ==========================================================================

def test_the_generator_inventory_is_the_documents():
    """§7.4 corrects v1's inventory of fact: three generators, five
    invented club names. v1 asserted a check into existence and named
    two generators and four clubs; this is the check."""
    for name in SYNTHETIC_GENERATORS:
        assert callable(globals()[name]), name
    archive, corpus = _archive(), _corpus()
    used = (set(archive["home_key"].astype(str))
            | set(archive["away_key"].astype(str))
            | set(corpus["home_key"].astype(str))
            | set(corpus["away_key"].astype(str)))
    assert used == set(SYNTHETIC_CLUBS)
    assert "other" in used and "other" not in CLUBS
    ledger = _ledger()
    assert set().union(*ledger.values()) <= set(SYNTHETIC_CLUBS)


@pinned
def test_the_synthetic_clubs_are_absent_from_the_pinned_artifacts():
    """§7.4, the ancestry check made mechanical — the test v1 said
    existed and did not.

    §7.4 defines SYNTHETIC as "every one of its values is written literally in
    `epl/tests/test_evwiden.py`, or generated there by arithmetic over literals
    written there", and forbids any value read, copied, sampled or transformed
    from the pinned artifacts. Names that also occur in the real archive would
    make that claim uncheckable by inspection; none of the five does.
    """
    archive = pd.read_parquet(PINNED_ARCHIVE)
    corpus = pd.read_parquet(PINNED_CORPUS)
    real = (set(archive["home_key"].astype(str))
            | set(archive["away_key"].astype(str))
            | set(corpus["home_key"].astype(str))
            | set(corpus["away_key"].astype(str)))
    assert set(SYNTHETIC_CLUBS).isdisjoint(real), sorted(
        set(SYNTHETIC_CLUBS) & real)


def test_the_generators_read_nothing_from_the_pinned_artifacts(monkeypatch):
    """§7.4: "No value may be read, copied, sampled, transformed, or otherwise
    derived from" the pinned parquet, ledger or retro ledger.

    The two routes this repository reads them by are closed for the duration,
    so a generator that reached for one would raise rather than quietly
    succeed."""
    def refuse(*a, **k):
        raise AssertionError("a synthetic generator read a pinned artifact")

    monkeypatch.setattr(pd, "read_parquet", refuse)
    monkeypatch.setattr(pd, "read_json", refuse, raising=False)
    monkeypatch.setattr(pd, "read_csv", refuse)
    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)
    monkeypatch.setattr(Path, "open", refuse)
    corpus, archive, ledger = _world()
    assert len(corpus) and len(archive) and ledger


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
    assert ew.SCHEMA_ID == "epl-evwiden-3"
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
    assert ew.EXPECTED_TABLE_CELLS == 32
    assert ew.EXPECTED_TABLE_TREATED == 15
    assert ew.EXPECTED_TABLE_UNTOUCHED == 17
    assert sum(ew.EXPECTED_THIN_BY_SEASON.values()) == ew.EXPECTED_THIN
    assert (ew.EXPECTED_TABLE_TREATED + ew.EXPECTED_TABLE_UNTOUCHED
            == ew.EXPECTED_TABLE_CELLS)


def test_the_write_set_excludes_everything_the_house_protects():
    """§8.3 closes the set. A harness that writes `src/` is a harness that broke
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
    monkeypatch.setattr(ew, "REALISED_CONFIG_SHA256",
                        ew.realised_config_sha256(good))
    assert ew.assert_config_frozen(cfg=good)
    for broken in ({"seed": 1, "model": {"widening": ew.FROZEN_WIDENING}},
                   {"seed": ew.SEED,
                    "model": {"widening": {"mechanism": "a", "strength": 0.5}}},
                   {"seed": ew.SEED,
                    "model": {"widening": {"mechanism": "c", "strength": 0.9}}}):
        with pytest.raises(ew.ConfigNotFrozen):
            ew.assert_config_frozen(cfg=broken)


def test_the_realised_configuration_is_pinned_and_not_only_the_frozen_file(
        monkeypatch):
    """§0.1: `frozen_wcmodel_config()` loads the LIVE `config/config.yaml` and
    overlays only the frozen EPL Elo block, so the decay half-life that DEFINES
    `e`, the volatility window `e* = 10.0` is taken from, the likelihood and the
    whole ADVI block came from a file no check bound.

    `ConfigNotFrozen` now fires on four conditions, not three, and the fourth is
    a digest of the configuration the run actually realises.
    """
    monkeypatch.setattr(ew, "CONFIG_SHA256", ew.sha256_file(ew.CONFIG_PATH))
    good = {"seed": ew.SEED,
            "model": {"widening": {"mechanism": "c", "strength": 0.5}}}
    digest = ew.realised_config_sha256(good)
    monkeypatch.setattr(ew, "REALISED_CONFIG_SHA256", digest)
    assert ew.assert_config_frozen(cfg=good)

    drifted = dict(good)
    drifted["windows"] = {"decay_half_life_days": 180}
    with pytest.raises(ew.ConfigNotFrozen) as exc:
        ew.assert_config_frozen(cfg=drifted)
    assert "realised" in str(exc.value)


@pinned
def test_the_pinned_realised_config_digest_is_the_documents():
    """§0.1 pins `78a51cd9…`, computed 2026-08-27 under the pinned frozen file.
    A drift there changes `e`, the posteriors, or reproducibility while the
    superseded three-condition check passed."""
    from epl import freeze

    assert ew.REALISED_CONFIG_SHA256 == (
        "78a51cd92c48838a57e3d6832b7661aad7a5b231425572214a067c2a35edbdcd")
    cfg = freeze.frozen_wcmodel_config()
    assert ew.realised_config_sha256(cfg) == ew.REALISED_CONFIG_SHA256
    # and the fields §0.1 says it now binds
    assert cfg["windows"]["decay_half_life_days"] == 365
    assert cfg["elo"]["volatility_window"] == 10
    assert cfg["model"]["widening"] == {"mechanism": "c", "strength": 0.5}
    assert cfg["seed"] == ew.SEED


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
    """§8.3 step 2 hashes the membership; a reordering must not move a digest."""
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
            "control_max_abs_diff": 0.0, "control_mean_abs_diff": 0.0,
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
                       verbose=False)


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
    # §2.3: Arm B IS recomputed now — from the same posterior — and the corpus
    # is a separate block whose role says what it is.
    assert rows[0]["arm_b"]["recomputed"] is True
    assert "predict pass 1" in rows[0]["arm_b"]["source"]
    assert "control" in rows[0]["corpus_control"]["role"]
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
# 5. §7.3's seeded defects — each class of §5.1 alone, on synthetic data
# ==========================================================================

def test_seeded_defect_control_mismatch_stops_the_run(tmp_path):
    """§3.2: EXACT equality at the corpus's eight decimals. A 1e-8 perturbation
    is the smallest lie the corpus can be told, and it must still be caught —
    §10 makes widening the tolerance after a mismatch an invalidation."""
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
    """§8.3 step 3 and §10: an audit run is legitimate and gets its own directory,
    where every row is stamped harness_frozen: false."""
    corpus, played, ledger = _world()
    points = ew.fit_points(corpus, [CUT_A], check=False)
    # Two refusals stand over this now and both are correct. §8.6's
    # public-surface closure refuses the injected fitter at a preregistered
    # target before anything else runs, and the directory guard refuses the
    # WRITE independently — which is the one that matters for a run with no
    # seam in it at all.
    with pytest.raises(ew.EvWidenError) as exc:
        ew.run_fits(points, ew.EVWIDEN_DIR / "shard_00_of_01.jsonl", corpus,
                    fitter=_stub_fitter(corpus, played, ledger),
                    verbose=False)
    assert "public-surface closure" in str(exc.value)
    with pytest.raises(ew.EvWidenError) as exc:
        ew._guard_ledger_location(ew.EVWIDEN_DIR / "shard_00_of_01.jsonl",
                                  harness_frozen=False)
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

class _FakePosterior:
    """The smallest object the WHOLE production map will accept.

    §7.3 binds the direction canary to the production path, so this double
    carries the surface `draw_api.per_draw_rates` and `mean_grid_over_draws`
    actually read — a team index, `_post` for the fitted parameters, the
    covariate hook and the config — and `predict_scoreline` DELEGATES to
    `draw_api.production_grid`, exactly as `wcmodel.model.posterior.Posterior`
    does. A test that goes through it therefore exercises the shipped map end to
    end rather than a re-implementation of its last leg.

    `log_rate` moves both clubs' log-rates together, which is how the edge
    branch is reached: at a marginal mean below `widening._MEAN_EDGE_EPS` there
    is no interior max-entropy solution and `inflate_predictive` documents that
    it returns the grid unchanged.
    """

    def __init__(self, mechanism: str = "c", strength: float = 0.5,
                 log_rate: float = 0.2, n_draws: int = 2,
                 teams: tuple[str, ...] = ("a", "b")):
        self.provisional_teams: set[str] = set()
        self._cfg = {"widening": {"mechanism": mechanism, "strength": strength},
                     "neutral_home_adv_fraction": 0.5}
        self.teams = list(teams)
        self._idx = {t: i for i, t in enumerate(teams)}
        self.likelihood = "dixon_coles"
        s = int(n_draws)
        n = len(teams)
        # a spread of strengths across the clubs, so a three-club world is not
        # three copies of one fixture
        self._params = {
            "att": np.array([[0.05 - 0.05 * i] * s for i in range(n)]),
            "def": np.array([[0.02 - 0.02 * i] * s for i in range(n)]),
            "mu": np.array([float(log_rate)] * s),
            "home_adv": np.array([0.25] * s),
            "rho": np.array([-0.05] * s),
        }

    def _post(self, name):
        return self._params[name]

    def _covariate_offsets(self, covariates):
        return 0.0, 0.0

    def predict_scoreline(self, home, away, neutral=False):
        from wcmodel.model.draw_api import FixtureCtx, production_grid

        return production_grid(self, FixtureCtx(home=home, away=away,
                                                neutral=neutral,
                                                covariates=None,
                                                host_factor=None))

    def predict_1x2(self, home, away, neutral=False):
        from wcmodel.model.draw_api import grid_one_x_two

        return grid_one_x_two(self.predict_scoreline(home, away, neutral))


# ---- §3.2 / L12: the identity control EXERCISED, not reimplemented ---------

def _engine_world(post, *, pairs=None):
    """A one-block corpus whose stored rows ARE this posterior's own forecasts.

    §3.2's control demands exact equality at eight decimals, so the corpus is
    generated from the posterior under the incumbent set rather than invented
    beside it: anything else would make the control fail for the wrong reason.
    """
    clubs = list(post.teams)
    pairs = pairs or [(clubs[0], clubs[1]), (clubs[1], clubs[0])]
    with ew.provisional_as(post, ()):
        stored = ew.predict_rows(post, pairs)
    rows = []
    for i, ((home, away), probs) in enumerate(zip(pairs, stored)):
        rows.append({
            "match_id": f"m{i}", "season": "2019/20", "block": "2019/20|W01",
            "date": pd.Timestamp("2019-08-10"), "home_key": home,
            "away_key": away, "y": i % 3,
            "dc_home": probs[0], "dc_draw": probs[1], "dc_away": probs[2],
            "dc_rps": float(score_mod.rps(np.array([probs]),
                                          np.array([i % 3]))[0]),
        })
    return pd.DataFrame(rows), pairs


def _bare_engine(post, corpus, *, monkeypatch, evidence=None, ledger=None,
                 cold=()):
    """The REAL `Engine`, with only the sampler replaced.

    §3.2, conformance row L12: "**These checks must be exercised directly, in
    the production code path.** The in-tree audit of v1 established that
    loosening `Engine.fit`'s exact comparison to a `1e-4` tolerance left the
    entire suite green, because the stub fitter in the tests reimplements the
    control rather than exercising it — and §10 makes widening that tolerance
    after a mismatch an invalidation, so the untested site is exactly the site
    where it would be widened."

    The constructor is bypassed because it builds a store and an anchor from the
    real archive; every attribute `Engine.fit` reads is supplied here, and the
    body that runs is the committed one.
    """
    import types

    from epl import dcfit
    from epl import walkforward as wf

    played = pd.DataFrame([{
        "match_id": "h0", "date": pd.Timestamp("2019-01-01"),
        "home_key": "a", "away_key": "b", "fthg": 1, "ftag": 0,
        "played": True, "season": "hist"}])

    class _Info:
        provisional_teams = set()
        cold_start_teams = list(cold)
        n_training_matches = 1
        n_teams = 2
        anchor_spec = "stub"
        seconds = 0.0

    monkeypatch.setattr(dcfit, "fit_epl",
                        lambda *a, **k: (post, _Info()))
    monkeypatch.setattr(wf, "_health", lambda p, cfg: {
        "all_finite": True, "sigma_positive": True, "home_adv_sane": True})

    engine = object.__new__(ew.Engine)
    engine.played = played
    engine.corpus = corpus
    engine.directory = None
    engine.can_fit = True
    engine.harness_frozen = False
    engine.cfg = post._cfg
    engine.store = object()
    engine.anchor = object()
    engine.ledger = ledger if ledger is not None else {}
    engine.evidence = evidence or {"2019/20|W01": {"a": 50.0, "b": 50.0}}
    engine.verbose = False
    engine._epl_fit = types.SimpleNamespace(
        assert_point_in_time=lambda store, cutoff: {
            "latest_training_date": "2019-01-01"})
    return engine


def _engine_point(corpus):
    return ew.FitPoint(cutoff="2019-08-10", season="2019/20",
                       block="2019/20|W01",
                       match_ids=tuple(corpus["match_id"].astype(str)))


def test_the_real_engine_fit_runs_the_identity_control_first(monkeypatch):
    """§3.2: "the control runs first, and not one treated prediction is produced
    until it passes" — asserted against the committed `Engine.fit`, which no v1
    test executed at all."""
    post = _FakePosterior()
    corpus, _ = _engine_world(post)
    engine = _bare_engine(post, corpus, monkeypatch=monkeypatch)
    out = engine.fit(_engine_point(corpus))
    assert out["control_max_abs_diff"] == 0.0
    assert out["provisional_incumbent"] == []


def test_the_real_engine_fit_refuses_a_difference_no_tolerance_would_see(
        monkeypatch):
    """L12(a): "loosen the eight-decimal comparison to a tolerance — [it] must
    turn a test red."

    The corruption is 1e-9, which every plausible tolerance swallows and
    `np.array_equal` does not. Loosening the comparison to `worst > 1e-4` —
    the exact seed the audit ran — turns this red.

    THE EVIDENCE MAKES `a` THIN, so the §2.1 union ADDS a club. The audit's
    follow-up finding was that this test went red for the wrong reason: with an
    empty `added` set the loosened comparison fell through to the identity-canary
    branch and raised `CanaryFailed`, so the site §10 names — "the identity
    control's tolerance is widened after a mismatch" — was satisfied by accident.
    With a club added that branch does not run, and the loosened comparison
    leaves nothing to raise at all.
    """
    post = _FakePosterior()
    corpus, _ = _engine_world(post)
    corpus.loc[0, "dc_home"] = float(corpus.loc[0, "dc_home"]) + 1e-9
    engine = _bare_engine(post, corpus, monkeypatch=monkeypatch,
                          evidence={"2019/20|W01": {"a": 0.5, "b": 50.0}})
    with pytest.raises(ew.ControlMismatch) as exc:
        engine.fit(_engine_point(corpus))
    assert "EXACT equality" in str(exc.value)


def test_the_real_engine_fit_refuses_an_untreated_fixture_that_moved(
        monkeypatch):
    """L12(b): "disable the `UntreatedMoved` loop — [it] must turn a test red."

    The seeded defect is a predicate that is not per-fixture: this posterior
    widens EVERY fixture as soon as its provisional set is non-empty, so a
    fixture the rule does not name moves. That is precisely what the loop is
    for — "a fixture that moves without being named means the predicate is not
    per-fixture, and every untreated delta this run reports would be noise
    dressed as zero".
    """
    class _Leaky(_FakePosterior):
        def predict_scoreline(self, home, away, neutral=False):
            from wcmodel.model.draw_api import finalize_grid

            return finalize_grid(ew.pre_widening_grid(self, home, away), self,
                                 provisional=bool(self.provisional_teams))

    # THREE clubs, so the block carries a fixture the rule does not name: `a`
    # is thin and `b` v `c` is not treated at all.
    post = _Leaky(teams=("a", "b", "c"))
    corpus, _ = _engine_world(post, pairs=[("a", "b"), ("b", "c")])
    engine = _bare_engine(post, corpus, monkeypatch=monkeypatch,
                          evidence={"2019/20|W01": {"a": 0.5, "b": 50.0,
                                                    "c": 50.0}})
    with pytest.raises(ew.UntreatedMoved) as exc:
        engine.fit(_engine_point(corpus))
    assert "outside the treated set" in str(exc.value)


def test_the_real_engine_fit_refuses_a_pass_two_pass_three_disagreement(
        monkeypatch):
    """L12(c): "disable the pass-2/pass-3 agreement check — [it] must turn a
    test red."

    The seeded defect is a mix that reads WHICH club carried the flag: this
    posterior's widening strength grows with the size of the provisional set, so
    pass 2 (the §2.1 union) and pass 3 (every club) give a treated fixture two
    different numbers. "Widening is a per-fixture boolean and the mix does not
    read which club carried it; if it did, the grid secondaries assembled from
    this pass would not be the arms they claim to be."
    """
    class _CountsClubs(_FakePosterior):
        def predict_scoreline(self, home, away, neutral=False):
            from wcmodel.model.draw_api import finalize_grid

            provisional = home in self.provisional_teams \
                or away in self.provisional_teams
            # the defect: the mix reads HOW MANY clubs carried the flag. It is
            # invisible to the direction canary, which always asks with a set of
            # size one, and it is exactly what pass 2 against pass 3 catches:
            # the §2.1 union names one club here, the all-clubs pass names two.
            kept = self._cfg["widening"]["strength"]
            if provisional and len(self.provisional_teams) >= 2:
                self._cfg["widening"]["strength"] = 0.6
            try:
                return finalize_grid(ew.pre_widening_grid(self, home, away),
                                     self, provisional=provisional)
            finally:
                self._cfg["widening"]["strength"] = kept

    post = _CountsClubs()
    corpus, _ = _engine_world(post)
    engine = _bare_engine(post, corpus, monkeypatch=monkeypatch,
                          evidence={"2019/20|W01": {"a": 0.5, "b": 50.0}})
    with pytest.raises(ew.EvWidenError) as exc:
        engine.fit(_engine_point(corpus),
                   grid_treated=[str(m) for m in corpus["match_id"]])
    assert "per-fixture boolean" in str(exc.value)


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


def test_the_pre_widening_grid_is_read_out_of_the_production_functions():
    """§7.3's comparator needs the grid `finalize_grid` is HANDED, and takes it
    from `draw_api`'s own two legs rather than re-deriving it: a canary built on
    a second implementation of the map checks the second implementation."""
    from wcmodel.model.draw_api import finalize_grid

    post = _FakePosterior()
    grid = ew.pre_widening_grid(post, "a", "b")
    with ew.provisional_as(post, ()):
        base = np.asarray(post.predict_scoreline("a", "b"), dtype=float)
    assert np.array_equal(finalize_grid(grid.copy(), post, provisional=False),
                          base)


def test_direction_canary_is_bound_to_the_production_path_and_the_frozen_alpha():
    """§7.3: the comparator is `finalize_grid(grid, posterior, provisional=…)`,
    equality is BIT equality, and the frozen alpha stays checkable because the
    production output must also equal `inflate_predictive(grid, True, 0.5)`
    renormalised the way `finalize_grid` renormalises it."""
    post = _FakePosterior()
    out = ew.direction_canary(post, [("a", "b")], treated=["a"])
    assert out["PASS"] is True
    assert out["max_abs_grid_diff"] == 0.0
    assert out["max_abs_diff_vs_frozen_alpha"] == 0.0
    assert out["min_entropy_gain_interior"] > 0.0
    assert out["alpha"] == ew.WIDENING_ALPHA
    assert "finalize_grid" in out["comparator"]
    # the branch every fixture took is recorded
    assert out["branches"] == [{"home": "a", "away": "b", "treated": True,
                                "branch": "interior",
                                "entropy_gain": out["detail"][0]["entropy_gain"],
                                "max_abs_dp": out["detail"][0]["max_abs_dp"],
                                "ok": True}]
    assert out["n_interior"] == 1 and out["n_edge"] == 0
    assert out["n_treated_interior"] == 1


def test_the_direction_canary_accepts_the_documented_edge_branch():
    """§7.3: `inflate_predictive` documents an edge no-op — a marginal mean at
    ~0 has no interior max-entropy solution and the grid is returned unchanged —
    so "strictly higher entropy" is not unconditional. An edge fixture with an
    unchanged grid and an equal entropy is the CORRECT result."""
    post = _FakePosterior(log_rate=-30.0)
    grid = ew.pre_widening_grid(post, "a", "b")
    assert float((grid.sum(axis=1) * np.arange(grid.shape[0])).sum()) < 1e-9
    with pytest.raises(ew.CanaryFailed) as exc:
        ew.direction_canary(post, [("a", "b")])
    assert "every fixture took the documented edge branch" in str(exc.value)
    # ...and the record says so rather than calling it a mechanism failure
    try:
        ew.direction_canary(post, [("a", "b")])
    except ew.CanaryFailed as err:
        assert "interior branch reached = False" in str(err)


def test_the_direction_canary_needs_one_treated_fixture_in_the_interior_branch():
    """§7.3: "A direction canary in which every fixture took the edge branch is
    CanaryFailed: it proved nothing." The same holds when the interior fixtures
    are all untreated — the treated grids are the ones under test."""
    post = _FakePosterior()
    # every fixture interior, and the treated club plays one of them
    assert ew.direction_canary(post, [("a", "b")], treated=["b"])["PASS"]
    # a treated club nobody in this block plays is not a demand on this block
    assert ew.direction_canary(post, [("a", "b")], treated=["z"])["PASS"]


def test_seeded_defect_a_widening_that_does_not_widen_fails_the_direction_canary():
    """Under mechanism (a) `finalize_grid` applies no predict-time mix, so the
    "widened" grid is the base grid: same numbers, zero entropy gain — and the
    fixture is in the INTERIOR branch, where that is a failure."""
    post = _FakePosterior(mechanism="a")
    with pytest.raises(ew.CanaryFailed) as exc:
        ew.direction_canary(post, [("a", "b")])
    assert "entropy gain" in str(exc.value)


def test_seeded_defect_a_mix_at_the_wrong_strength_fails_the_direction_canary():
    """§2.1 freezes alpha at 0.5. A grid mixed at another strength is a
    different treatment from the preregistered one, and §7.3's move onto the
    production path does not lose that check."""
    post = _FakePosterior(strength=0.25)
    with pytest.raises(ew.CanaryFailed) as exc:
        ew.direction_canary(post, [("a", "b")], strength=ew.WIDENING_ALPHA)
    assert "frozen alpha" in str(exc.value)


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
# 7. the evidence canary — §7.3's two legs, and its positive control
# ==========================================================================

def test_evidence_canary_passes_on_a_sound_frame():
    played = _archive()
    clubs = list(CLUBS)
    out = ew.evidence_canary(played, CUT_B, clubs)
    assert out["PASS"] is True
    assert out["negative_leg_max_abs_diff"] == 0.0
    assert out["positive_control_max_abs_diff"] > 1e-9
    assert out["provisional_checked"] is False


def test_the_negative_leg_is_array_equal_and_both_legs_count_their_rows():
    """§7.3: the comparison is `numpy.array_equal` on the float64 values BEFORE
    rounding — bit equality, not a tolerance — and "both legs record the number
    of rows the mask selected; an empty mask is a refusal, never a pass"."""
    played = _archive()
    out = ew.evidence_canary(played, CUT_B, list(CLUBS))
    assert out["negative_leg_array_equal"] is True
    assert "array_equal" in out["comparator"]
    n_after = int(ew.corrupt_mask(played, CUT_B, side="after").sum())
    n_before = int(ew.corrupt_mask(played, CUT_B, side="before").sum())
    assert out["negative_leg_rows_selected"] == n_after > 0
    assert out["positive_control_rows_selected"] == n_before > 0
    assert n_after + n_before == len(played)
    # §7.3's frozen mutation, on the record beside the numbers
    assert out["mutation"]["fthg"] == 9 and out["mutation"]["ftag"] == 9
    assert out["mutation"]["dates"] == "not touched"


def test_the_negative_leg_refuses_a_difference_no_tolerance_would_see():
    """A bound rather than a tolerance: one ULP of movement in the evidence
    vector is a leak, and `array_equal` is what makes it one."""
    played = _archive()
    real = ew.effective_evidence

    def nudged(cutoff, frame, clubs=None, **kwargs):
        out = real(cutoff, frame, clubs, **kwargs)
        if any(str(k).startswith(ew._CANARY_PREFIX)
               for k in frame["home_key"].astype(str)):
            first = sorted(out)[0]
            out[first] = np.nextafter(out[first], np.inf)
        return out

    import unittest.mock as mock

    with mock.patch.object(ew, "effective_evidence", nudged):
        with pytest.raises(ew.EvidenceCanaryFailed) as err:
            ew.evidence_canary(played, CUT_B, list(CLUBS))
    assert "array_equal = False" in str(err.value)


def test_the_evidence_canary_corrupts_clubs_and_not_only_scores():
    """`e` never reads a score, so a score-only corruption would pass on a
    BROKEN filter. Reassigning the clubs is what makes the negative leg able
    to fail."""
    played = _archive()
    after = ew.corrupt_archive(played, CUT_B, side="after")
    late = after.loc[pd.to_datetime(after["date"]) >= pd.Timestamp(CUT_B)]
    assert len(late)
    assert all(str(k).startswith(ew._CANARY_PREFIX) for k in late["home_key"])
    assert all(str(k).startswith(ew._CANARY_PREFIX) for k in late["away_key"])
    # unique per row: `valid_played_results` collapses content-identical rows
    # (same date, same unordered pair, same goals map) as its duplicate-match
    # dedup, so a corruption that repeated one club pair would DELETE the rows
    # it meant to rewrite and the canary would crash instead of measuring
    assert len(set(late["home_key"])) == len(late)


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
    """§7.3 demands "every `e(t, C)` and BOTH provisional sets bit-identical"."""
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
    """§7.3: "An `e*` low enough to add nobody must yield `np.array_equal` with
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
    """The paired deltas, recomputed from the ROWS' own probabilities.

    §2.3: Arm B is `probs_incumbent` — the SAME posterior under the fit's own
    recomputed incumbent set — and not the corpus's stored row.
    """
    out = {}
    for r in rows:
        if float(r["e_min"]) >= e_star:
            continue
        y = int(r["y"])
        a = float(score_mod.rps(np.array([r["probs_arm"]]), np.array([y]))[0])
        b = float(score_mod.rps(np.array([r["probs_incumbent"]]),
                                np.array([y]))[0])
        out[r["match_id"]] = a - b
    return out


def test_arm_b_is_the_same_posteriors_incumbent_pass_and_never_the_corpus():
    """§2.3, the repair that makes the pairing real.

    The superseded design took Arm B out of the corpus — an old ROUNDED 1X2
    projection — while Arm A came from a new fit, and mechanism (c) acts on the
    full scoreline grid BEFORE that projection. Two grids can agree at eight
    decimals after projection and respond differently to `inflate_predictive`.

    Both arms now come from one posterior and one base grid. This test proves it
    where the identity control cannot mask it: `_fixture_row` is handed a fit
    whose incumbent pass DIFFERS from the stored corpus row, and the delta must
    follow the incumbent pass.
    """
    corpus = _corpus()
    point = ew.FitPoint(season="2019/20", block="2019/20|2020W02", cutoff=CUT_A,
                        match_ids=("m001",))
    row = corpus.set_index(corpus["match_id"].astype(str)).loc["m001"]
    native = [float(row[c]) for c in ew._PROB_COLUMNS]
    incumbent = [round(native[0] - 0.01, 8), round(native[1] + 0.01, 8),
                 round(native[2], 8)]
    arm = [round(incumbent[0] - 0.02, 8), round(incumbent[1] + 0.02, 8),
           round(incumbent[2], 8)]
    out = {
        "pairs": [("rich", "mid")], "evidence": {"rich": 50.0, "mid": 5.0},
        "probs_incumbent": np.array([incumbent]), "probs_arm": np.array([arm]),
        "probs_widened": {}, "provisional_incumbent": [], "treated": ["m001"],
    }
    made = ew._fixture_row(point, 0, out, row, {"realised_config_sha256": "r",
                                                "harness_sha256": "h",
                                                "archive_rows": 1,
                                                "archive_sha256": "a",
                                                "ledger_sha256": "l",
                                                "wall_seconds": 0.0},
                           key="k", config_sha="c", shard_id="0/1",
                           harness_frozen=False, e_star=ew.E_STAR,
                           grid=ew.E_GRID)
    y = int(row["y"])
    rps = lambda p: float(score_mod.rps(np.array([p]), np.array([y]))[0])  # noqa: E731

    assert made["probs_incumbent"] == incumbent
    assert made["rps_B"] == pytest.approx(rps(incumbent))
    assert made["rps_arm"] == pytest.approx(rps(arm))
    # the estimand's delta is Arm A minus the SAME posterior's incumbent pass
    assert made["delta"] == pytest.approx(rps(arm) - rps(incumbent))
    # ...and the corpus survives only as the control, side by side
    assert made["rps_native"] == pytest.approx(rps(native))
    assert made["delta_vs_corpus"] == pytest.approx(rps(arm) - rps(native))
    assert made["delta"] != pytest.approx(made["delta_vs_corpus"])
    assert made["max_abs_dp_vs_corpus"] == pytest.approx(
        max(abs(a - b) for a, b in zip(incumbent, native)))
    assert made["arm_b"]["recomputed"] is True
    assert "corpus" in made["corpus_control"]["role"]


def test_the_corpus_is_the_external_control_at_full_strength(tmp_path):
    """§2.3: "The corpus is demoted to an external identity control." All 820
    fixtures must still equal Arm B at their eight decimals, and each stored
    `dc_rps` must still re-derive from its own stored probabilities.

    The consequence §2.3 pre-states, so it cannot be discovered later: because
    the control demands eight-decimal equality and stops the run otherwise, the
    repaired delta can differ from the superseded one by at most the eighth
    decimal, per fixture. Both are published."""
    rows = _merged(tmp_path)
    for r in rows:
        assert r["probs_incumbent"] == r["probs_native"]
        assert float(r["max_abs_dp_vs_corpus"]) == 0.0
        assert float(r["delta"]) == pytest.approx(float(r["delta_vs_corpus"]),
                                                  abs=1e-12)


def test_the_estimand_is_the_mean_paired_delta_over_the_thin_population(tmp_path):
    rows = _merged(tmp_path)
    hand = _hand_deltas(rows)
    result = ew.estimand(rows, corpus_rows=len(rows))
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
    result = ew.estimand(rows, corpus_rows=len(rows))
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
    result = ew.estimand(rows, corpus_rows=2280)
    full = result["secondaries"]["full_population"]
    assert full["mean"] == pytest.approx(result["mean"] * result["n"] / 2280)
    assert full["decides"] == "nothing"


def test_both_intervals_are_reported_and_they_use_different_blocks(tmp_path):
    """§2.3 requires both and §4.1 gates on both: the season interval's job is
    to refuse a result carried by one season."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, corpus_rows=len(rows))
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
        [str(r["block"]) for r in thin], n_boot=ew.N_BOOT, alpha=ew.ALPHA,
        seed=ew.BOOTSTRAP_SEED)
    result = ew.estimand(rows, corpus_rows=len(rows))
    assert result["ci95"] == [lo, hi]
    assert result["n_blocks"] == n


def test_the_grid_is_assembled_from_the_same_fits_and_agrees_at_the_primary(
        tmp_path):
    """§3.1: "each point's thin-population mean delta, treated count, and
    week-block CI, FROM THE SAME 78 FITS"."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, corpus_rows=len(rows))
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
        ew.estimand(rows, corpus_rows=len(rows))
    assert "widened probabilities" in str(exc.value)


def test_the_structural_zero_guard_is_two_sided_at_the_merge(tmp_path):
    """§2.3, conformance row L13. "**The structural-zero guard is two-sided at
    the merge.** Every merged row that is **not** in the treated set must carry
    a delta of exactly 0.0 — this covers both classes, and both are refusals."

    v1's `stray` scan refused only the first class, fixtures with
    `e_min >= e*`. The audit found the hole: "A THIN but already-incumbent-
    widened fixture (33 of the 85, which §2.3 states 'carry a delta of exactly
    0.0 by construction') carrying a non-zero delta is not refused — it is
    averaged straight into the estimand and into the treated-subset arithmetic
    §2.3 relies on."

    That arithmetic is the whole reason the 85-population's mean is a known
    multiple of the treated mean: "the 33 are exactly the rows whose zero-ness
    makes the 85-population's mean a known multiple of the treated mean".
    """
    # class one: outside the thin population entirely
    rows = _merged(tmp_path)
    stray = next(r for r in rows if float(r["e_min"]) >= ew.E_STAR)
    stray["delta"] = 1e-9
    with pytest.raises(ew.UntreatedMoved) as exc:
        ew.estimand(rows, corpus_rows=len(rows))
    assert "e_min >= e*" in str(exc.value) or "outside the thin" in str(exc.value)

    # class two: THIN, but already widened by the incumbent predicate — the
    # class v1 averaged straight in
    rows = _merged(tmp_path)
    widened = next(r for r in rows if float(r["e_min"]) < ew.E_STAR
                   and bool(r["incumbent_widened"]))
    widened["delta"] = 1e-9
    with pytest.raises(ew.UntreatedMoved) as exc:
        ew.estimand(rows, corpus_rows=len(rows))
    assert "ALREADY WIDENS" in str(exc.value)


def test_the_two_always_pass_controls_are_measured_off_the_merged_rows(
        tmp_path):
    """§9.1, conformance row L17. "**The two controls that v1 hard-coded are
    measured.** `controls.untreated_moved` and `controls.predicate_mismatch`
    must be **read off the merged rows** [...] not written as
    `{n: 0, PASS: true}` constants. Their values are true by construction only
    because a refusal stops the run first; a verdict file that always prints
    PASS for a control nobody measured is exactly the shape this document's own
    'a test that cannot fail is not a test' objects to."
    """
    rows = _merged(tmp_path)
    clean = ew.measured_controls(rows)
    assert clean["untreated_moved"]["n"] == 0
    assert clean["untreated_moved"]["PASS"] is True
    assert clean["predicate_mismatch"]["n"] == 0
    assert clean["predicate_mismatch"]["PASS"] is True

    # one row of each class, each MEASURED rather than assumed away
    dirty = [dict(r) for r in rows]
    stray = next(r for r in dirty if not bool(r["treated"]))
    stray["delta"] = 1e-9
    mismatched = dirty[0]
    mismatched["fit"] = {**mismatched["fit"],
                         "provisional_incumbent": ["rich"],
                         "provisional_ledger": ["mid"]}
    measured = ew.measured_controls(dirty)
    assert measured["untreated_moved"]["n"] >= 1
    assert measured["untreated_moved"]["PASS"] is False
    assert measured["predicate_mismatch"]["n"] >= 1
    assert measured["predicate_mismatch"]["PASS"] is False

    # ...and the published object carries what was measured, not a constant
    published = ew.evidence_object({"controls": measured})
    assert published["controls"]["untreated_moved"]["n"] >= 1
    assert published["controls"]["untreated_moved"]["PASS"] is False
    assert published["controls"]["predicate_mismatch"]["PASS"] is False


def test_seeded_defect_a_population_that_is_not_the_pre_stated_one_refuses(
        tmp_path):
    """§2.3 fixes the population and forbids dropping a fixture for any reason."""
    rows = _merged(tmp_path)
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.estimand(rows, corpus_rows=len(rows), expected_thin=85)
    assert "not the pre-stated 85" in str(exc.value)


def test_the_strata_read_the_category_off_the_models_own_cold_start_verdict(
        tmp_path):
    """§3.1's two categories: returning-thin vs cold-start tail, decided by
    `epl.dcfit.cold_start_clubs`'s own verdict recorded on the fit row, not by
    a list of club names typed into the harness."""
    rows = _merged(tmp_path)
    cold = ew.cold_start_club_seasons(rows)
    assert ("2019/20", "cold") in cold
    result = ew.estimand(rows, corpus_rows=len(rows))
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
    result = ew.estimand(rows, corpus_rows=len(rows))
    movement = result["secondaries"]["movement"]
    assert movement["max_abs_prob_shift"] > 0
    assert movement["reseed_scale"]["pooled_shift"] == 0.000075
    assert movement["reseed_scale"]["source"] == "reports/epl_walkforward.md"


def test_the_realised_power_is_reported_beside_the_frozen_scenarios(tmp_path):
    """§6 supersedes §2.3's "No power claim is made in advance": the analysis
    was done, blind, and is committed code. What the estimand carries is the
    other half §6 requires — "after the run, the REALISED paired SD of the
    treated deltas and the MDE recomputed at it" — which decides nothing and
    moves no threshold, beside the three frozen scenarios and §6's warning."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, corpus_rows=len(rows))
    power = result["power"]
    realised = power["realised"]
    assert realised["mde_80pct_two_sided_5pct"] == pytest.approx(
        realised["multiplier"] * realised["se_iid"])
    assert realised["sd_paired_treated"] is not None
    assert "NOT gate" in realised["note"]
    assert [s["scenario"] for s in power["frozen_scenarios"]] == [
        "A freshness-scale", "B anchoring-scale", "C mechanism-scale"]
    assert "SUBSTANTIALLY UNINFORMATIVE" in power["warning"]
    assert power["decides"].startswith("nothing")
    assert result["decides"].startswith("nothing")
    assert result["secondaries_decide"] == "nothing"


def _tiny_power_structure():
    """A small structure of the frozen SHAPE, for tests about the machinery.

    §6.2's structure is "recomputed from the pinned artifacts by the harness
    itself, not typed in", and §6.5's realised re-run keeps `R`, both seeds, the
    grid and the interpolation rule frozen — the structure is the thing a test
    may shrink, and the pinned tests exercise the real one.
    """
    blocks = [f"b{i // 2}" for i in range(12)]
    seasons = [f"s{i // 4}" for i in range(12)]
    treated = np.array([i % 2 == 0 for i in range(12)], dtype=bool)
    return {"blocks": blocks, "seasons": seasons, "treated": treated,
            "n_thin": 12, "n_treated": int(treated.sum()),
            "n_week_blocks": len(set(blocks)), "n_seasons": len(set(seasons))}


def test_the_joint_gate_mde_is_recomputed_at_the_realised_sd(tmp_path):
    """§6.5's obligation, which v1 reported the wrong quantity for.

    > After the run, the **realised paired SD of the treated deltas** is
    > reported, and **the joint-gate MDE is recomputed at that realised SD** —
    > the fixed-scenario simulation of §6.2 re-run with `s` set to the realised
    > value, at the same `R`, the same seeds, the same grid and the same
    > interpolation rule, producing a realised `power@bar`, realised `MDE80` and
    > realised ratio in the same columns as §6.3's table.
    >
    > It is a distinct quantity from the two-sided-test-against-zero MDE, which
    > is not what gate (i) is; **a result document that reports the latter
    > beside the realised SD has not discharged this obligation.**

    v1 reported exactly the latter: `2.8016 × se_iid`, beside a sentence saying
    the joint MDE "remains the fixed-scenario simulation's". The joint one is
    now computed.
    """
    rows = _merged(tmp_path)
    result = ew.estimand(rows, corpus_rows=len(rows))
    sd = result["power"]["realised"]["sd_paired_treated"]
    assert sd is not None

    joint = ew.realised_power(sd, structure=_tiny_power_structure())
    assert [r["rho"] for r in joint["rows"]] == list(ew.POWER_RHOS)
    for row in joint["rows"]:
        assert row["scenario"] == "realised"
        assert row["sd"] == pytest.approx(float(sd))
        # the SAME columns as §6.3's table
        assert set(row) >= {"power_at_bar", "mde_estimand", "ratio_to_bar",
                            "power_at_2x_bar"}
    # the same R, the same seeds, the same grid, the same interpolation rule
    assert joint["replicates"] == ew.POWER_REPLICATES
    assert joint["simulation_seed"] == ew.POWER_SEED
    assert joint["bootstrap"]["seed"] == ew.BOOTSTRAP_SEED
    assert joint["grid"]["points"] == ew.POWER_GRID_POINTS

    # ...and the evidence object carries it under `power.realised`, beside — not
    # instead of — the two-sided quantity it is distinct from
    obj = ew.evidence_object({**result, "table": {}},
                             power={"structure": {}, "rows": []})
    realised = obj["power"]["realised"]
    assert realised["sd_paired_treated"] == sd
    assert realised["joint_mde"]["rows"]
    assert "NOT gate" in realised["note"]
    # §6.5: the joint MDE is RECOMPUTED at the realised SD. v1's note said it
    # "remains the fixed-scenario simulation's", which is the obligation
    # restated as a refusal to meet it — and §6.5 names that exact shape as not
    # discharging it.
    assert "power_simulation()'s" not in realised["note"]
    assert "recomputed at the realised SD" in realised["note"]
    assert "joint_mde" in realised["note"]


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
                    harness_frozen=True, require_canaries=False)
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
    """§10: a run that precedes the §6 freeze commit is not this experiment."""
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


def test_seeded_defect_a_corpus_row_that_is_not_the_corpus_refuses(tmp_path):
    """§2.3: the corpus is the EXTERNAL identity control. A row that copies
    different numbers under that name has nothing left to control against."""
    _run(tmp_path)
    _freeze_rows(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows[0]["probs_native"] = [0.4, 0.3, 0.3]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        _merge(tmp_path)
    assert "identity control" in str(exc.value)


def test_seeded_defect_an_arm_b_that_drifted_from_the_corpus_refuses(tmp_path):
    """§3.2, as §2.3 restates it: all 820 fixtures of the 78 openings must equal
    Arm B at their eight decimals, and the merge re-checks it rather than
    trusting the run's own inline control."""
    _run(tmp_path)
    _freeze_rows(tmp_path)
    path = tmp_path / ew.shard_name(0, 1)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows[0]["probs_incumbent"] = [round(v + 1e-8, 8)
                                  for v in rows[0]["probs_incumbent"]]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ew.ControlMismatch) as exc:
        _merge(tmp_path)
    assert "eight decimals" in str(exc.value)


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
    """§7.3 and RUN_ORDER: the preconditions gate the NUMBER, not the wall
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

    # a merge that asserts the freeze also demands the RESULTS canary: the
    # audit's --no-results-canary may not follow the run past §6's commit
    ew.write_canaries({"PASS": True, "evidence": {"PASS": True}},
                      tmp_path / ew.CANARY_NAME)
    with pytest.raises(ew.CanaryFailed) as exc:
        _merge(tmp_path, require_canaries=True)
    assert "--no-results-canary" in str(exc.value)

    ew.write_canaries({"PASS": True, "evidence": {"PASS": True},
                       "results": {"PASS": True}, "results_canary_run": True},
                      tmp_path / ew.CANARY_NAME)
    assert _merge(tmp_path, require_canaries=True)["n_fixtures"] == 8


# ==========================================================================
# 11. the table-retro leg — §3.3's identity demand and §4.1 (iv)'s gate
# ==========================================================================

#: The synthetic table world mirrors v3 §3.3's own shape: seven seasons x five
#: labels MINUS §0.6's three unpriceable cells = 32 cells, with §4.1's census
#: of treated cells per label — MW0 2, MW3 2, MW6 **7**, MW10 4, MW19 **0** —
#: over a per-label CELL census of MW0 5, MW3 6, MW6 7, MW10 7, MW19 7. The
#: gates are per horizon, so a fixture-world that flattened the labels could
#: not exercise them, and one that kept seven cells per label could not
#: exercise the census v3 is scoped by.
TABLE_SEASONS = tuple(f"20{19 + i}/{20 + i}" for i in range(7))
TABLE_LABELS = ("MW0", "MW3", "MW6", "MW10", "MW19")
TABLE_CLUBS = ("sunderland", "rich", "mid")

#: P particles, k seasons each: n_sims = P * k. Small enough to bootstrap in a
#: test, large enough that `ddof=1` means something.
TALLY_PARTICLES = 8
TALLY_SEASONS_PER_PARTICLE = 4
TALLY_N_SIMS = TALLY_PARTICLES * TALLY_SEASONS_PER_PARTICLE


def _tally(shift: int, *, jitter: int = 0, particles: int = TALLY_PARTICLES,
           k: int = TALLY_SEASONS_PER_PARTICLE, clubs: int = 3) -> np.ndarray:
    """A per-particle fractional rank-mass tally with honest margins.

    Every particle's tally is `k` times a permutation matrix, so every club row
    and every rank column sums to `k` — the equal-cluster condition §5.2
    enforces and `epl.simmetrics.trps_se_cluster` enforces on its own input.
    `jitter = 0` makes every particle identical, so the bootstrap has exactly
    zero variance and a gate test can be about the gate; `jitter > 0` makes the
    particles differ and the standard error real.
    """
    out = np.zeros((particles, clubs, clubs), dtype=float)
    for s in range(particles):
        rot = (shift + (s % (jitter + 1))) % clubs
        for c in range(clubs):
            out[s, c, (c + rot) % clubs] = float(k)
    return out


def _cells(seasons=TABLE_SEASONS, labels=TABLE_LABELS):
    """v3 §3.3's 32 cells, with §4.1's per-label treated census."""
    treated_by_label = dict(ew.EXPECTED_TREATED_BY_LABEL)
    out = []
    for label in labels:
        seen = 0
        for i, season in enumerate(seasons):
            if f"{season}|{label}" in ew.EXCLUDED_CELLS:
                continue
            treated = (["sunderland"]
                       if seen < treated_by_label.get(label, 0) else [])
            seen += 1
            out.append({
                "season": season, "cutoff_label": label,
                "cutoff": f"20{19 + i}-08-{10 + TABLE_LABELS.index(label):02d}",
                "clubs": list(TABLE_CLUBS),
                "provisional_incumbent": ["rich"],
                "provisional_enlarged": sorted(["rich"] + treated),
                "treated_clubs": treated,
                "evidence": {"sunderland": 0.17, "rich": 50.0, "mid": 5.0},
            })
    return out


def _parity_for(cells):
    """The protected runner's digests, as `run_parity_oracle` would return them."""
    return {f"{c['season']}|{c['cutoff_label']}": {
        "key": f"{c['season']}|{c['cutoff_label']}",
        "substantive_digest": f"sub-{c['season']}-{c['cutoff_label']}",
        "provisional_teams": ["rich"],
        # §3.3 compares this as a FIELD, and the comparison may not fail open:
        # a side that is absent is a side that did not match.
        "effective_posterior_hash": "book"} for c in cells}


def _table_runner(shift: float = -0.001, *, break_identity: str | None = None,
                  jitter: int = 0, break_parity: bool = False,
                  break_provisional: bool = False):
    """A stub cell runner with the repaired `TableRunner` output contract."""

    def run(cell, parity_row=None):
        treated = list(cell["treated_clubs"])
        key = f"{cell['season']}|{cell['cutoff_label']}"
        base = 0.08 + 0.0001 * TABLE_LABELS.index(cell["cutoff_label"])
        delta = shift if treated else 0.0
        sampler_c = f"sampler-{key}"
        sampler_t = sampler_c if not treated else sampler_c + "-t"
        if break_identity == "untouched" and not treated:
            sampler_t = sampler_c + "-moved"
        if break_identity == "treated" and treated:
            sampler_t = sampler_c
        sub_c = f"sub-{cell['season']}-{cell['cutoff_label']}"
        if break_parity:
            sub_c += "-drifted"
        prov_c = ["rich"]
        prov_t = sorted(set(prov_c) | set(treated))
        if break_provisional:
            prov_t = sorted(set(prov_t) | {"mid"})

        def arm(name, trps, sampler, sub, provisional):
            return {"trps": trps, "wtrps": trps * 1.1, "flat_trps": 0.2,
                    "sampler_digest": sampler, "substantive_digest": sub,
                    "effective_posterior_hash": "book",
                    "provisional": provisional,
                    "coverage": {"coverage50": 0.5, "coverage90": 0.9},
                    "coverage_treated": {c: {"coverage50": 0.6,
                                             "coverage90": 0.95}
                                         for c in treated},
                    "clubs_detail": {c: {"p_relegated": 0.6, "points_mean": 30.0,
                                         "points_sd": 14.1, "points_p5": 12.0,
                                         "points_p95": 50.0,
                                         "points_realised": 25}
                                     for c in treated},
                    "n_sims": TALLY_N_SIMS, "n_particles": TALLY_PARTICLES,
                    "tally_check": {"sims_per_particle":
                                    TALLY_SEASONS_PER_PARTICLE},
                    "widening_mode": "per_fixture_bernoulli@alpha=0.5"}

        return {
            "schema": ew.SCHEMA_ID, "season": cell["season"],
            "cutoff_label": cell["cutoff_label"], "cutoff": cell["cutoff"],
            "clubs": cell["clubs"], "treated_clubs": treated,
            "provisional_incumbent": cell["provisional_incumbent"],
            "provisional_enlarged": cell["provisional_enlarged"],
            "provisional_control": prov_c, "provisional_treatment": prov_t,
            "evidence": cell["evidence"], "n_sims": TALLY_N_SIMS,
            "seed": 20260611,
            "arms": {"control": arm("control", base, sampler_c, sub_c, prov_c),
                     "treatment": arm("treatment", base + delta, sampler_t,
                                      sub_c + "-t", prov_t)},
            "identical": ew.assert_table_identity(
                treated, sampler_c, sampler_t, where=key),
            "realised_hash": "realised",
            "realised_positions": {c: i + 1 for i, c in enumerate(TABLE_CLUBS)},
            "realised_spans": {c: 1 for c in TABLE_CLUBS},
            "realised_points": {c: 40 - 5 * i for i, c in enumerate(TABLE_CLUBS)},
            "consequence_weights": [1.0, 1.0],
            "harness_sha256": "stub",
            "_tallies": {"control": _tally(0, jitter=jitter),
                         "treatment": _tally(1 if treated else 0,
                                             jitter=jitter)},
        }

    return run


def _run_cells(tmp_path, cells=None, *, runner=None, name="table.jsonl",
               **kwargs):
    """Run the stub table leg with a stub parity oracle beside it."""
    cells = _cells() if cells is None else cells
    path = Path(tmp_path) / name
    ew.run_table(cells, path, runner=runner or _table_runner(),
                 parity=_parity_for(cells), config_sha="c", verbose=False,
                 **kwargs)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return path, rows


def test_the_untouched_cells_must_prove_they_did_not_move():
    """§3.3: "the other 19 cells are unchanged by construction, AND THE HARNESS
    MUST PROVE IT" — on the SAMPLER digest (§3.3(a))."""
    assert ew.assert_table_identity([], "d", "d", where="cell") is True
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_table_identity([], "d", "other", where="cell")
    assert "unchanged BY CONSTRUCTION" in str(exc.value)


def test_a_treated_cell_that_did_not_move_is_the_absence_of_the_experiment():
    """§3.3(4) as §3.3(a) restates it so that it can actually FAIL: with the
    provisional set outside the digest, equality is a statement about
    scorelines, tie blocks and points — the things the D12 branch moves."""
    assert ew.assert_table_identity(["x"], "d", "e", where="cell") is False
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_table_identity(["x"], "d", "d", where="cell")
    assert "never reached the sampler" in str(exc.value)
    assert "SAMPLER OUTPUT" in str(exc.value)


def test_the_provisional_set_is_a_compared_field_and_not_a_digest_ingredient():
    """§3.3(a) ends v1's tautology: the digest included the provisional
    set, and §3.3(4) then used digest inequality as proof that the treatment
    reached the sampler. Those two prove nothing together. Metadata is checked
    as metadata now."""
    ew.assert_provisional_fields(["x"], ["a"], ["a", "x"], where="cell")
    ew.assert_provisional_fields([], ["a"], ["a"], where="cell")
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_provisional_fields(["x"], ["a"], ["a"], where="cell")
    assert "compared field" in str(exc.value)
    with pytest.raises(ew.TableIdentityBreak):
        ew.assert_provisional_fields(["x"], ["a"], ["a", "x", "y"], where="cell")
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_provisional_fields([], ["a"], ["a", "b"], where="cell")
    assert "untouched cells" in str(exc.value)


# ---- §3.3: the digests, and the call into protected code ------------------

class _FakePlan:
    def __init__(self, clubs, n_sims, n_particles, seed=20260611):
        self.season = "2019/20"
        self.season_code = "1920"
        self.cutoff = "2019-08-09"
        self.observed_by = "2019-08-09T00:00:00Z"
        self.clubs = tuple(clubs)
        self.fixtures = tuple(
            _FakeFixture(f"f{i}", i, clubs[i % len(clubs)],
                         clubs[(i + 1) % len(clubs)],
                         None if i else (1, 0))
            for i in range(2))
        self.adjustments = np.zeros(len(clubs), np.int16)
        self.boundaries = ((1, 1), (2, 3))
        self.rule_id = "handbook-v1"
        self.n_sims = int(n_sims)
        self.n_particles = int(n_particles)
        self.seed = int(seed)
        self.chunk_size = 8
        self.n_unresolved = 0
        self.results_lag = False


class _FakeFixture:
    def __init__(self, fixture_id, ordinal, home, away, result):
        self.fixture_id = fixture_id
        self.ordinal = ordinal
        self.home_key = home
        self.away_key = away
        self.result = result


class _FakeRows:
    def __init__(self, block_start, block_span, particle, n_clubs):
        n = len(block_start)
        self.block_start = np.asarray(block_start, np.uint8)
        self.block_span = np.asarray(block_span, np.uint8)
        self.resolution_code = np.zeros((n, n_clubs), np.uint8)
        self.order = np.tile(np.arange(n_clubs, dtype=np.int8), (n, 1))
        self.particle = np.asarray(particle, np.int64)
        self.points = np.zeros((n, n_clubs), np.int16)
        self.gd = np.zeros((n, n_clubs), np.int16)
        self.gf = np.zeros((n, n_clubs), np.int16)


class _FakeRun:
    """The surface `particle_tallies` and the two digests read, and no more."""

    def __init__(self, *, n_clubs=3, particles=4, k=2, tie=False):
        n = particles * k
        # season i puts club c at position c+1, except a tied pair when asked
        start, span = [], []
        for i in range(n):
            if tie and i % 2 == 0:
                start.append([1, 1, 3])
                span.append([2, 2, 1])
            else:
                start.append(list(range(1, n_clubs + 1)))
                span.append([1] * n_clubs)
        particle = [i % particles for i in range(n)]
        self.retained_rows = _FakeRows(start, span, particle, n_clubs)
        self.plan = _FakePlan([f"c{i}" for i in range(n_clubs)], n, particles)
        self.n_sims = n
        self.n_particles = particles
        from epl import table as table_mod

        ranking = table_mod.Ranking(
            block_start=self.retained_rows.block_start,
            block_span=self.retained_rows.block_span,
            resolution_code=self.retained_rows.resolution_code,
            order=self.retained_rows.order,
            boundaries=self.plan.boundaries, rule_id=self.plan.rule_id)
        self.matrix = table_mod.position_mass(ranking).sum(axis=0) / n


def test_the_tally_is_fractional_rank_mass_and_never_reads_order():
    """§5 supersedes §5.3's tally bullet. `.order` is "the deterministic
    club-index order" inside a shared block and carries no meaning; the matrix
    TRPS scores is built from `position_mass`'s fractional `1/span`."""
    run = _FakeRun(tie=True)
    tallies = ew.particle_tallies(run)
    assert tallies.shape == (run.n_particles, 3, 3)
    # a tie block of two clubs spreads 1/2 across both positions
    assert set(np.unique(tallies)) <= {0.0, 0.5, 1.0, 1.5, 2.0}
    # scrambling `order` cannot move the tally: nothing reads it
    scrambled = _FakeRun(tie=True)
    scrambled.retained_rows.order = scrambled.retained_rows.order[:, ::-1].copy()
    assert np.array_equal(ew.particle_tallies(scrambled), tallies)


def test_the_chunked_tally_is_bit_identical_to_the_unchunked_one():
    """§5: "a committed test asserts that equality at 0.0". `numpy.add.at` is
    unbuffered and applies its indices in order, so contiguous ascending chunks
    perform the same sequence of additions as one pass."""
    run = _FakeRun(particles=4, k=8, tie=True)
    whole = ew.particle_tallies(run, chunk_size=10_000)
    for size in (1, 3, 7, 32):
        assert float(np.abs(ew.particle_tallies(run, chunk_size=size)
                            - whole).max()) == 0.0


def test_the_tally_binds_the_matrix_and_refuses_an_unequal_cluster():
    """§5's two committed checks: the tally reproduces the scored matrix, and
    every particle is an equal cluster of complete seasons."""
    run = _FakeRun(tie=True)
    tallies = ew.particle_tallies(run)
    check = ew.assert_tally_binds_the_matrix(tallies, run)
    assert check["max_abs_matrix_diff"] <= 1e-9
    assert check["sims_per_particle"] == run.n_sims / run.n_particles

    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.assert_tally_binds_the_matrix(tallies * 1.5, run)
    assert "does not reproduce the scored matrix" in str(exc.value)

    lopsided = tallies.copy()
    lopsided[0, 0, 0] += 1.0
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.assert_tally_binds_the_matrix(lopsided, run)
    assert "equal cluster" in str(exc.value) or "does not reproduce" in str(
        exc.value)


def test_the_sampler_digest_excludes_everything_but_the_sampler():
    """§3.3(a): "Nothing else. No club list, no plan, no seed, no posterior
    hash, NO PROVISIONAL SET, no arm label, no clocks, no host, no shard id, no
    free text." It is comparable only within one cell, between its two arms."""
    run = _FakeRun(tie=True)
    tallies = ew.particle_tallies(run)
    base = ew.sampler_digest(run, tallies)

    # the plan, the seed and the club names are outside it
    run.plan.seed = 999
    run.plan.clubs = ("z0", "z1", "z2")
    run.plan.chunk_size = 4096
    assert ew.sampler_digest(run, tallies) == base
    # the sampler's own output is inside it
    moved = run.retained_rows.points.copy()
    moved[0, 0] += 1
    run.retained_rows.points = moved
    assert ew.sampler_digest(run, tallies) != base


def test_the_substantive_digest_binds_the_whole_plan_state():
    """§3.3(b): season/cutoff/`observed_by` identity, the fixture-and-result
    snapshot, the adjustments, the rule id, the chunking (which fixes the RNG
    chunk keys and therefore the numbers) and the results-lag state."""
    run = _FakeRun()
    tallies = ew.particle_tallies(run)
    kw = dict(weights=[1.0, 1.0], boundaries=run.plan.boundaries,
              realised_hash="r", realised_positions=[1, 2, 3],
              realised_points=[40, 30, 20])
    base = ew.substantive_digest(run, tallies, **kw)

    state = ew.plan_state(run)
    assert set(state) == {"season", "season_code", "cutoff", "observed_by",
                          "clubs", "fixtures", "adjustments", "boundaries",
                          "rule_id", "n_sims", "n_particles", "seed",
                          "chunk_size", "n_unresolved", "results_lag"}
    for field, value in (("chunk_size", 4096), ("observed_by", "later"),
                         ("rule_id", "other"), ("results_lag", True),
                         ("n_unresolved", 2)):
        run = _FakeRun()
        setattr(run.plan, field, value)
        assert ew.substantive_digest(run, ew.particle_tallies(run),
                                     **kw) != base, field
    # ...and the provisional set is NOT in it — that is the digest split
    assert "provisional" not in ew.plan_state(_FakeRun())


def test_the_sampler_digests_signature_is_pinned_to_run_and_tallies():
    """§3.3, conformance row L11, and it is here because a two-line change got
    past the whole suite.

    > **`sampler_digest`'s signature is pinned.** A committed test asserts
    > `list(inspect.signature(sampler_digest).parameters) == ['run',
    > 'tallies']`, and a second committed test at `TableRunner` level asserts
    > that **two books differing only in `provisional`, over identical retained
    > rows, produce EQUAL sampler digests**. Both are required because the
    > in-tree audit of v1 showed that a two-line change adding `provisional` to
    > the digest's payload left the whole suite green while turning the
    > treated-cell identity test into a test that cannot fail — the exact
    > tautology the digest split exists to end.

    "A test that only checks which *existing* fields move the digest cannot see
    a new input channel; these two can."
    """
    import inspect

    assert list(inspect.signature(ew.sampler_digest).parameters) == [
        "run", "tallies"]


def test_two_books_differing_only_in_provisional_hash_the_same_sampler_output():
    """§3.3's second committed test, at the level the audit named.

    The seed that went green against v1 was `sampler_digest(run, tallies, *,
    provisional=())` with `TableRunner` passing `book.provisional`. At a treated
    cell `control.provisional != treatment.provisional`, so the two arms'
    digests differ because the METADATA differs — and
    `assert_table_identity`'s treated-cell condition becomes a test that cannot
    fail, "reporting a zero delta as evidence of no harm when the treatment
    never reached the sampler".

    This test drives the runner's own per-arm record with two books differing in
    nothing but `provisional`, over ONE run and ONE tally, and requires the
    sampler digests to be EQUAL and the provisional field to differ.
    """
    run = _FakeRun()
    tally = ew.particle_tallies(run)

    class _Book:
        def __init__(self, provisional):
            self.provisional = frozenset(provisional)
            self.alpha = 0.5
            self.n_particles = int(run.n_particles)

        def content_hash(self):
            return "the same posterior either way"

    control = ew.arm_record(run, tally, _Book({"rich"}), clubs=["a", "b", "c"],
                            positions=np.array([1, 2, 3]),
                            spans=np.array([1, 1, 1]),
                            truth=np.array([40, 30, 20]),
                            weights=[1.0, 1.0], realised_hash="r",
                            treated_clubs=[])
    treatment = ew.arm_record(run, tally, _Book({"rich", "sunderland"}),
                              clubs=["a", "b", "c"],
                              positions=np.array([1, 2, 3]),
                              spans=np.array([1, 1, 1]),
                              truth=np.array([40, 30, 20]),
                              weights=[1.0, 1.0], realised_hash="r",
                              treated_clubs=["sunderland"])

    assert control["provisional"] != treatment["provisional"]
    assert control["sampler_digest"] == treatment["sampler_digest"]
    # ...and the substantive digest is equally blind to it, for the same reason
    assert control["substantive_digest"] == treatment["substantive_digest"]


def test_the_substantive_digest_excludes_the_effective_posterior_hash():
    """§3.3, and the reason is arithmetic rather than taste.

    > **Why `effective_posterior_hash` is excluded from the payload.** It is
    > supplied as `ParticleBook.content_hash()`, and `content_hash` hashes
    > `sorted(self.provisional)` (`epl/particles.py:331-358`). Embedding it
    > would re-admit the provisional set into a digest the document says
    > excludes it — directly contradicting the definition, whatever the
    > downstream consequence.

    v1 passed it in and listed it as item 8, so the digest that "excludes the
    provisional set by name" hashed the provisional set at one remove.
    """
    import inspect

    from epl import particles

    params = inspect.signature(ew.substantive_digest).parameters
    assert "effective_posterior_hash" not in params

    # the mechanism, not the claim: content_hash hashes `_meta()`, and `_meta`
    # carries `sorted(self.provisional)` — which is why embedding the hash
    # re-admits exactly what the digest's definition excludes
    assert "_meta()" in inspect.getsource(particles.ParticleBook.content_hash)
    assert "sorted(self.provisional)" in inspect.getsource(
        particles.ParticleBook._meta)

    run = _FakeRun()
    tallies = ew.particle_tallies(run)
    kw = dict(weights=[1.0, 1.0], boundaries=run.plan.boundaries,
              realised_hash="r", realised_positions=[1, 2, 3],
              realised_points=[40, 30, 20])
    assert ew.substantive_digest(run, tallies, **kw) == \
        ew.substantive_digest(run, tallies, **kw)
    # §3.3's replacement: the posterior identity is not discarded, it becomes a
    # separately-recorded and separately-COMPARED provenance field
    oracle = {"substantive_digest": "abc", "provisional_teams": ["rich"],
              "effective_posterior_hash": "book"}
    assert ew.assert_native_parity("2019/20|MW6", "abc", oracle, ["rich"],
                                   effective_posterior="book")["PASS"] is True
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_native_parity("2019/20|MW6", "abc", oracle, ["rich"],
                                effective_posterior="a different book")
    assert "effective posterior" in str(exc.value)


def test_the_table_runner_calls_protected_simulate_with_its_own_signature():
    """§3.3 recorded the defect rather than fixing it quietly: the harness
    called `leaguesim.simulate` with the particle book in `state`'s argument
    position and no `seed` at all, while protected `epl/simretro.py:555` calls
    it `simulate(arm, state, provider, n_sims, seed, …)`."""
    import inspect

    from epl import leaguesim

    order = list(inspect.signature(leaguesim.simulate).parameters)
    assert order[:6] == ["arm", "state", "book_or_provider", "n_sims", "seed",
                         "chunk_size"]

    seen = {}

    def spy(*args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return "run"

    import unittest.mock as mock

    # §2.3's closure and §8.6's: `n_sims`, the simulation seed and the chunk
    # size are not parameters of this surface — it RESOLVES them from the
    # frozen law — and the played frame is required so the guard can key on the
    # artifact identity, which is the whole of what the review's NEW-B2 found
    # missing here.
    frozen = ew.frozen_table_constants()
    assert frozen == {"n_sims": 20_000, "seed": 20260611,
                      "chunk_size": frozen["chunk_size"]}
    assert not ({"n_sims", "seed", "chunk_size"}
                & set(inspect.signature(ew.simulate_arm).parameters))
    with mock.patch.object(leaguesim, "simulate", spy):
        out = ew.simulate_arm("STATE", "BOOK", played=_archive(),
                              n_particles=5)
    assert out == "run"
    assert seen["args"] == (ew.TABLE_ARM_LABEL, "STATE", "BOOK",
                            frozen["n_sims"], frozen["seed"],
                            frozen["chunk_size"])
    assert seen["kwargs"] == {"n_particles": 5}
    bound = inspect.signature(leaguesim.simulate).bind(*seen["args"],
                                                       **seen["kwargs"])
    assert bound.arguments["state"] == "STATE"
    assert bound.arguments["book_or_provider"] == "BOOK"
    assert bound.arguments["seed"] == frozen["seed"]


# ---- §3.3 / §3.3(c): the 35-cell native-parity oracle ---------------------

def test_the_parity_oracle_compares_substantive_digests_and_the_incumbent_set():
    """§3.3: binding the SCHEDULE to protected code binds neither its semantics
    nor its call, and the 19-untouched-cell control compares two arms produced
    by the SAME new code, so shared drift passes it silently."""
    oracle = {"substantive_digest": "abc", "provisional_teams": ["rich"],
              "effective_posterior_hash": "book"}
    assert ew.assert_native_parity("2019/20|MW6", "abc", oracle, ["rich"],
                                   effective_posterior="book")["PASS"] is True
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_native_parity("2019/20|MW6", "def", oracle, ["rich"],
                                effective_posterior="book")
    assert "native parity at all thirty-two priceable cells" in str(exc.value)
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_native_parity("2019/20|MW6", "abc", oracle, ["rich", "mid"],
                                effective_posterior="book")
    assert "control arm IS the incumbent arm" in str(exc.value)

    # ...and the effective-posterior comparison MAY NOT FAIL OPEN. The
    # superseded version compared "only when both hashes are non-null", so a
    # side that carried none passed a check it never ran.
    for ours, theirs in ((None, "book"), ("book", None), (None, None)):
        with pytest.raises(ew.TableIdentityBreak) as exc:
            ew.assert_native_parity(
                "2019/20|MW6", "abc",
                dict(oracle, effective_posterior_hash=theirs), ["rich"],
                effective_posterior=ours)
        assert "fails OPEN" in str(exc.value)


def test_the_parity_oracle_runs_every_cell_and_resumes(tmp_path):
    cells = _cells()
    seen = []

    def stub(cell):
        seen.append(f"{cell['season']}|{cell['cutoff_label']}")
        return {"key": seen[-1], "season": cell["season"],
                "cutoff_label": cell["cutoff_label"],
                "substantive_digest": f"sub-{seen[-1]}",
                "provisional_teams": ["rich"]}

    path = tmp_path / "parity.jsonl"
    out = ew.run_parity_oracle(cells, path, runner=stub, verbose=False)
    assert len(out) == len(cells) == 32
    assert len(seen) == 32
    again = ew.run_parity_oracle(cells, path, runner=stub, verbose=False)
    assert len(seen) == 32 and len(again) == 32     # resumed, not re-run


def test_no_require_parity_parameter_and_no_limit_on_the_oracle_exist():
    """§3.3's closures 2 and 3, conformance row L5.

    > **No `--limit` on the oracle.** No CLI flag, keyword or subset argument
    > may reduce the oracle's 32 cells. "All 32" is the whole content of the
    > control.
    >
    > **No `require_parity` parameter exists.** An exposed boolean that turns
    > the oracle off is a bypass; the document does not permit one and the
    > harness may not carry one. Parity is a property of the run, not an option
    > of the caller.
    """
    import inspect

    assert "require_parity" not in inspect.signature(ew.run_table).parameters
    for fn in (ew.run_table, ew.run_parity_oracle):
        params = set(inspect.signature(fn).parameters)
        assert not {p for p in params
                    if "limit" in p or "sample" in p or "subset" in p}, fn
    # ...and `--table` no longer takes the CLI flag that truncated the 35
    assert "--table --limit" not in ew.launch_script()


def test_parity_is_established_before_one_treated_simulation_runs(tmp_path):
    """§3.3's closure 1, conformance row L5: "call the table leg with an oracle
    of 34 cells and with none; each must raise `TableIdentityBreak` **before**
    any treatment simulation runs".

    v1's `run_parity_oracle` produced protected rows first, but the new runner
    then simulated control AND TREATMENT and only afterwards compared its
    control against protected output. "A design in which the new runner
    simulates control **and treatment** and only then compares the control
    against protected output has already executed the treatment before
    establishing parity, and does not satisfy this clause."
    """
    cells = _cells()
    for oracle in ({}, _parity_for(cells[:-1])):
        simulated = []

        def counting(cell, parity_row=None, _inner=_table_runner()):
            simulated.append(cell["season"] + "|" + cell["cutoff_label"])
            return _inner(cell, parity_row)

        with pytest.raises(ew.TableIdentityBreak) as exc:
            ew.run_table(cells, tmp_path / "t.jsonl", runner=counting,
                         parity=oracle, config_sha="c", verbose=False)
        assert "before" in str(exc.value).lower()
        assert simulated == [], simulated       # not ONE arm of ONE cell


def test_the_treated_run_refuses_a_control_arm_that_drifted_from_protected(
        tmp_path):
    cells = _cells()
    with pytest.raises(ew.TableIdentityBreak):
        ew.run_table(cells, tmp_path / "t.jsonl",
                     runner=_table_runner(break_parity=True),
                     parity=_parity_for(cells), config_sha="c", verbose=False)


def test_every_table_row_records_the_digest_of_its_own_tally_file(tmp_path):
    """§8.7: "**every table ledger row records the SHA-256 of its own tally
    file**, written at the same moment as the row"."""
    path, rows = _run_cells(tmp_path)
    assert "tally_sha256" in ew._TABLE_ROW_FIELDS
    assert "tally_sha256" in ew._TABLE_COLUMNS
    for row in rows:
        target = ew.tally_path(path, row)
        assert target.exists()
        assert row["tally_sha256"] == ew.sha256_file(target)


def test_a_swapped_tally_is_refused_on_the_digest_and_on_its_invariants(
        tmp_path):
    """§8.7, conformance row L10. "Each is a live deciding input: §5's estimator
    and §5.4's unanimity rule read them, and a structurally valid replacement
    could alter the MC standard errors — and turn UNRESOLVED into PASS —
    without changing any other digest."

    v1 wrote the 32 deciding arrays as NPZ sidecars and reloaded them checking
    "neither their digest against the ledger nor their matrix/tally invariant
    before using them to decide P1–P5". Both checks are now on every read.
    """
    path, rows = _run_cells(tmp_path)
    row = next(r for r in rows if r["treated_clubs"])

    # a read of the untouched file rebinds cleanly
    ew.load_tallies(path, row)

    # ...and a STRUCTURALLY VALID replacement — a different but legal tally —
    # is refused on the recorded digest
    target = ew.tally_path(path, row)
    with np.load(target) as data:
        payload = {k: np.asarray(data[k]) for k in data.files}
    payload["treatment"] = _tally(2)
    np.savez_compressed(target, **payload)
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.load_tallies(path, row)
    assert "digest" in str(exc.value)

    # and a replacement that also forges the row's digest is still refused,
    # because §5.1's two binding checks are re-run on every read
    broken = dict(row)
    broken["tally_sha256"] = ew.sha256_file(target)
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.load_tallies(path, broken)
    assert "matrix" in str(exc.value) or "cluster" in str(exc.value)


def test_an_absent_tally_file_is_a_refusal_and_never_a_smaller_bootstrap(
        tmp_path):
    """§7.1 lists "a tally file that is absent or fails its recorded digest"
    under `TableMCImprecise`."""
    path, rows = _run_cells(tmp_path)
    row = rows[0]
    ew.tally_path(path, row).unlink()
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.load_tallies(path, row)
    assert "not on disk" in str(exc.value)


def test_the_table_leg_writes_one_row_per_cell_and_resumes(tmp_path):
    cells = _cells()
    path = tmp_path / "table.jsonl"
    out = ew.run_table(cells, path, runner=_table_runner(),
                       parity=_parity_for(cells), config_sha="c", verbose=False)
    assert out["n_written"] == len(cells) == 32
    again = ew.run_table(cells, path, runner=_table_runner(),
                         parity=_parity_for(cells), config_sha="c",
                         verbose=False)
    assert again["n_written"] == 0 and again["n_skipped"] == len(cells)
    # the tallies live beside the ledger, because a [P, C, C] array is not a
    # JSONL field and §5 needs all thirty-two at once
    assert ew.tally_path(path, {"season": "2019/20",
                                "cutoff_label": "MW6"}).exists()


# ---- §4.1: the deciding statistics are per horizon -------------------------

def test_the_pooled_35_cell_statistic_is_gone_from_every_deciding_path(tmp_path):
    """§4.1: the 35-cell pooled ΔTRPS and ΔwTRPS are WITHDRAWN from the
    published outputs entirely, not demoted to secondaries. Protected code
    freezes "Never averaged across cutoffs" and publishing the average invites
    it to be quoted as a verdict."""
    path, rows = _run_cells(tmp_path)
    scored = ew.score_table(rows, ledger_path=path)
    assert "pooled_delta_trps" not in scored
    assert "pooled_delta_wtrps" not in scored
    assert "withdrawn" in scored
    gate = ew.table_gate(scored)
    assert "pooled" not in json.dumps(gate["iv_a"])
    assert "pooled" not in json.dumps(gate["iv_b"])
    assert "pooled" not in json.dumps(gate["iv_c"])
    assert "decides nothing" in gate["withdrawn"]


def test_the_deciding_statistics_are_the_named_horizon_and_the_point_gates(
        tmp_path):
    """§4.1 (iv-a): the equal-weight mean over the SEVEN MW6 cells. (iv-b): at
    MW0, MW3 and MW10, the mean over THAT LABEL'S TREATED CELLS ONLY."""
    path, rows = _run_cells(tmp_path, runner=_table_runner(shift=-0.001))
    scored = ew.score_table(rows, ledger_path=path)
    assert scored["mw6"]["n"] == 7
    assert scored["mw6"]["mean"] == pytest.approx(-0.001)     # all seven treated
    assert scored["per_label"]["MW0"]["n_treated"] == 2
    assert scored["per_label"]["MW3"]["n_treated"] == 2
    assert scored["per_label"]["MW10"]["n_treated"] == 4
    for label in ("MW0", "MW3", "MW10"):
        assert scored["per_label"][label]["mean"] == pytest.approx(-0.001)
        assert "no interval" in scored["per_label"][label]["interval"]
    assert scored["mw19"]["structural_zero"] is True
    assert scored["mw19"]["n_treated"] == 0
    assert scored["mw19"]["decides"] == "nothing"


def test_the_mw6_interval_is_r_b3s_frozen_construction(tmp_path):
    """§5.3's table: `epl.score.block_bootstrap_ci`, the seven season strings
    one cell per block, B = 10,000, alpha = 0.05, seed 20260814, NumPy's default
    linear-interpolation quantile."""
    path, rows = _run_cells(tmp_path)
    scored = ew.score_table(rows, ledger_path=path)
    mw6 = scored["mw6"]
    assert mw6["n_blocks"] == ew.TABLE_CI_BLOCKS == 7
    assert mw6["bootstrap"]["function"] == "epl.score.block_bootstrap_ci"
    assert mw6["bootstrap"]["seed"] == ew.BOOTSTRAP_SEED
    assert mw6["bootstrap"]["alpha"] == ew.ALPHA
    deltas = np.array([c["delta_trps"] for c in mw6["per_cell"]], dtype=float)
    seasons = [c["season"] for c in mw6["per_cell"]]
    lo, hi, n = score_mod.block_bootstrap_ci(deltas, seasons, n_boot=ew.N_BOOT,
                                             alpha=ew.ALPHA,
                                             seed=ew.BOOTSTRAP_SEED)
    assert mw6["ci95"] == [lo, hi] and n == 7


# ---- §5: the jointly resampled, tie-aware paired bootstrap --------------

def _mc_cells(n=2, *, jitter=1, particles=TALLY_PARTICLES, label="MW6"):
    positions = np.array([1, 2, 3])
    spans = np.array([1, 1, 1])
    return [{"key": f"2019/2{i}|{label}", "cutoff_label": label,
             "positions": positions, "spans": spans,
             "control": _tally(0, jitter=jitter, particles=particles),
             "treatment": _tally(1, jitter=jitter, particles=particles)}
            for i in range(n)]


def test_the_paired_bootstrap_applies_one_index_to_every_tally():
    """§5: "There is no quadrature step and no independence claim anywhere in
    this estimator." The label mean is computed INSIDE each replicate, so cells
    that move together in the run move together in the replicate.

    v1's `sqrt(sum se^2)/7` would shrink a perfectly correlated pair by
    `1/sqrt(2)`; the joint estimator does not, and that is the whole repair."""
    cells = _mc_cells(n=2, jitter=1)
    out = ew.paired_mc_bootstrap(cells, seed=ew.MC_SEED)
    per_cell = list(out["mc_se_per_cell"].values())
    label = out["mc_se_label"]["MW6"]
    assert all(v > 0 for v in per_cell)
    # the two cells are byte-identical by construction, so the mean of their
    # deltas has exactly their own standard error — not the quadrature one
    assert label == pytest.approx(per_cell[0], rel=1e-12)
    quadrature = float(np.sqrt(sum(v ** 2 for v in per_cell)) / len(per_cell))
    assert label > quadrature


def test_the_paired_bootstrap_is_deterministic_at_its_frozen_seed():
    """...and the frozen seed is the ONLY seed it will run at.

    §2.3's closure covers the resampling seed as well as B, so the "a different
    seed gives a different answer" half of this test is now made by the refusal
    rather than by running the estimator twice — which is the stronger
    statement: a second seed is not reported as this experiment (§10).
    """
    cells = _mc_cells(n=2, jitter=1)
    a = ew.paired_mc_bootstrap(cells, seed=ew.MC_SEED)
    b = ew.paired_mc_bootstrap(cells, seed=ew.MC_SEED)
    assert a["mc_se_per_cell"] == b["mc_se_per_cell"]
    assert ew.MC_BOOT == 2000 and ew.MC_SEED == 20260827
    with pytest.raises(ew.EvWidenError) as exc:
        ew.paired_mc_bootstrap(cells, seed=ew.MC_SEED + 1)
    assert "not overridable" in str(exc.value)


def test_the_bootstrap_refuses_a_common_index_space_it_does_not_have():
    """§5.2: "Joint resampling is undefined without a common index
    space, and this document will not approximate one." `TableMCImprecise`."""
    mixed = _mc_cells(n=1) + _mc_cells(n=1, particles=TALLY_PARTICLES * 2)
    mixed[1]["key"] = "other|MW6"
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.paired_mc_bootstrap(mixed)
    assert "ONE common index space" in str(exc.value)

    lopsided = _mc_cells(n=1)
    lopsided[0]["control"] = lopsided[0]["control"].copy()
    lopsided[0]["control"][0, 0, 0] += 1.0
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.paired_mc_bootstrap(lopsided)
    assert "unequal season" in str(exc.value)


# ---- gate (iv), all three parts, and the precision rule --------------------

def _unanimous(point_verdict: bool, *, dissent: int = 0):
    """A §5.4 unanimity object that could have come from a real run.

    NEW-B3: `table_gate` used to trust "any truthy `mc.unanimity` with
    `fired=False`", validating "neither `K=200`, seed, 200 verdicts, nor
    dissent consistency" — so a fabricated `k=1` object could resolve PASS.
    It validates all of that now, one-directionally: an object that cannot be
    checked fires P5, which is UNRESOLVED.
    """
    verdicts = [point_verdict] * ew.UNANIMITY_K
    for i in range(dissent):
        verdicts[i] = not point_verdict
    return {"k": ew.UNANIMITY_K, "seed": ew.UNANIMITY_SEED,
            "verdicts": verdicts, "point_verdict": point_verdict,
            "dissenting": dissent, "fired": bool(dissent)}


def _scored(mean_mw6=0.0, ci=(-1.0, 1.0), means=(0.0, 0.0, 0.0), se=None,
            unanimity=None):
    labels = dict(zip(ew.POINT_GATE_LABELS, means))
    mc_se = {"MW6": 0.0, "MW0": 0.0, "MW3": 0.0, "MW10": 0.0}
    mc_se.update(se or {})
    point_verdict = bool(mean_mw6 > 0.0 and ci[0] > 0.0)
    if unanimity is None:
        # §5.4's default for a scored object that carries no unanimity run at
        # all: a P5 that was never computed is UNRESOLVED, never "small". The
        # tests that are about P1-P4 hand in an agreed one so the gate can
        # resolve on the condition they are actually about — and the gate now
        # VALIDATES it (K, seed, 200 recorded verdicts, its own dissent count
        # and this gate's own iv-c point verdict), so an agreed one has to be
        # a run that could have happened.
        unanimity = _unanimous(point_verdict)
    mc = {"mc_boot": ew.MC_BOOT, "mc_seed": ew.MC_SEED,
          "n_particles": 1000, "sims_per_particle": 20.0,
          "mc_se_label": mc_se, "mc_se_per_cell": {}}
    if unanimity != "absent":
        mc["unanimity"] = unanimity
    return {
        "n_cells": 35, "n_treated_cells": 16,
        "mw6": {"cutoff_label": "MW6", "n": 7, "mean": mean_mw6,
                "ci95": list(ci), "n_blocks": 7},
        "per_label": {lab: {"cutoff_label": lab, "n_treated": 3,
                            "mean": labels[lab]}
                      for lab in ew.POINT_GATE_LABELS},
        "mw19": {"structural_zero": True, "decides": "nothing"},
        "mc": mc,
    }


def test_gate_iv_a_is_the_mw6_mean_against_the_tolerance():
    assert ew.table_gate(_scored(mean_mw6=-0.001))["iv_a"]["PASS"] is True
    assert ew.table_gate(_scored(mean_mw6=0.0002))["iv_a"]["PASS"] is True
    assert ew.table_gate(_scored(mean_mw6=0.0003))["iv_a"]["PASS"] is False
    assert ew.table_gate(_scored(mean_mw6=0.0003))["verdict"] == "FAIL"


def test_gate_iv_b_is_a_point_gate_at_each_of_mw0_mw3_and_mw10():
    """§4.1: "No interval is computed at these labels and none is required; two
    cells do not carry one." MW19 decides nothing."""
    ok = ew.table_gate(_scored(means=(0.0, 0.0002, -0.001)))
    assert all(v["PASS"] for v in ok["iv_b"].values())
    assert ok["verdict"] == "PASS"
    bad = ew.table_gate(_scored(means=(0.0, 0.0, 0.0003)))
    assert bad["iv_b"]["MW10"]["PASS"] is False
    assert bad["verdict"] == "FAIL"
    assert bad["mw19"]["decides"] == "nothing"


def test_gate_iv_c_fails_only_a_resolvable_worsening():
    """(iv-c) fails if the MW6 mean is > 0 AND the interval's lower bound is
    > 0. An unresolvable wiggle passes; a small-but-resolvable worsening does
    not."""
    assert ew.table_gate(_scored(mean_mw6=0.00005,
                                 ci=(-0.0001, 0.0002)))["iv_c"]["PASS"] is True
    resolvable = ew.table_gate(_scored(mean_mw6=0.00005,
                                       ci=(0.00001, 0.0002)))
    assert resolvable["iv_c"]["PASS"] is False
    assert resolvable["verdict"] == "FAIL"


def test_the_precision_rule_guards_every_deciding_boundary():
    """§5's repair of the unguarded boundary: v1 guarded the
    comparison to +0.0002 and nothing else, while (iv-c) decides on two further
    boundaries against ZERO and (iv-b) on three more against the tolerance.
    Noise at any of them could turn a failing gate into a passing one."""
    # (P1) resolution
    p1 = ew.table_gate(_scored(mean_mw6=-0.01, ci=(-0.02, -0.005),
                               means=(-0.01, -0.01, -0.01),
                               se={"MW6": 6e-5}))
    assert p1["verdict"] == "UNRESOLVED" and "P1" in p1["precision"]["fired"]
    # (P2) iv-a's tolerance boundary
    p2 = ew.table_gate(_scored(mean_mw6=0.00019, ci=(-1.0, -0.5),
                               se={"MW6": 1e-5}))
    assert "P2" in p2["precision"]["fired"] and p2["verdict"] == "UNRESOLVED"
    # (P3) iv-b's tolerance boundaries, per label
    p3 = ew.table_gate(_scored(mean_mw6=-0.01, ci=(-0.02, -0.005),
                               means=(0.00019, -0.01, -0.01),
                               se={"MW0": 1e-5}))
    assert "P3.MW0" in p3["precision"]["fired"]
    # (P4) iv-c's zero boundary on the mean
    p4 = ew.table_gate(_scored(mean_mw6=1e-6, ci=(-1.0, -0.5),
                               se={"MW6": 1e-5}))
    assert "P4" in p4["precision"]["fired"]
    # (P5) iv-c's zero boundary on the interval — the UNANIMITY rule
    p5 = ew.table_gate(_scored(mean_mw6=-0.01, ci=(-0.02, -0.005),
                               unanimity=_unanimous(False, dissent=1)))
    assert "P5" in p5["precision"]["fired"]
    # ...and every one of them only ever REFUSES
    for out in (p1, p2, p3, p4, p5):
        assert out["PASS"] is False and out["resolved"] is False


def test_p5_is_the_unanimity_rule_and_never_a_scale_comparison():
    """§5.4's P5, frozen: "The whole of iv-c is recomputed on `K = 200`
    particle-resampled tally sets. [...] **P5 fires — and gate (iv) is
    UNRESOLVED — unless all 200 verdicts agree with each other and with the
    point-estimate verdict.** One dissenting `k` is enough."

    v1's P5 compared `|ci_lo_MW6 − 0|` with `2 × mc_se_mw6`, and §5.4 shows that
    comparison is invalid rather than merely stylistic: `mc_se_mw6` is the MC
    standard error of a LINEAR statistic — the equal-weight mean of seven cell
    deltas — while `ci_lo_MW6` is a NONLINEAR quantile of a season bootstrap
    over those same seven values. Cross-cell error proportional to
    `(+h, −h, 0, 0, 0, 0, 0)` leaves the mean error identically zero, so
    `mc_se_mw6` can be arbitrarily small, while unequal season-bootstrap
    multiplicities move the lower quantile across zero. The proxy then fails to
    fire while iv-c flips from FAIL to PASS — "precisely the direction that must
    never be available".
    """
    import inspect

    assert ew.UNANIMITY_K == 200 and ew.UNANIMITY_SEED == 20260828
    src = inspect.getsource(ew.table_gate)
    p5 = [line for line in src.splitlines() if '"P5"' in line]
    assert p5, src
    # the superseded proxy compared ci_lo against a multiple of mc_se_mw6
    assert not any("ci_lo" in line and "MC_BOUNDARY_SIGMAS" in line
                   for line in src.splitlines())

    # with no unanimity object at all, P5 is UNRESOLVED and never "small"
    absent = ew.table_gate(_scored(mean_mw6=-0.01, ci=(-0.02, -0.005),
                                   unanimity="absent"))
    assert "P5" in absent["precision"]["fired"]
    # ...and unanimity across all 200 lets it resolve
    agreed = ew.table_gate(_scored(
        mean_mw6=-0.01, ci=(-0.02, -0.005), unanimity=_unanimous(False)))
    assert "P5" not in agreed["precision"]["fired"]
    assert agreed["precision"]["unanimity_k"] == 200
    assert agreed["precision"]["unanimity_seed"] == 20260828
    assert agreed["precision"]["unanimity_dissenting"] == 0

    # NEW-B3: the gate used to trust "any truthy `mc.unanimity` with
    # `fired=False`", validating "neither `K=200`, seed, 200 verdicts, nor
    # dissent consistency" — so a FABRICATED object could resolve PASS. Every
    # one of these says `fired: False` and none of them may resolve the gate.
    for bad in ({"k": 1, "seed": ew.UNANIMITY_SEED, "verdicts": [False],
                 "point_verdict": False, "dissenting": 0, "fired": False},
                {"k": ew.UNANIMITY_K, "seed": ew.UNANIMITY_SEED + 1,
                 "verdicts": [False] * ew.UNANIMITY_K, "point_verdict": False,
                 "dissenting": 0, "fired": False},
                {"k": ew.UNANIMITY_K, "seed": ew.UNANIMITY_SEED,
                 "point_verdict": False, "dissenting": 0, "fired": False},
                dict(_unanimous(False, dissent=3), dissenting=0, fired=False),
                # scored against the OTHER point verdict than this gate's own
                _unanimous(True)):
        out = ew.table_gate(_scored(mean_mw6=-0.01, ci=(-0.02, -0.005),
                                    unanimity=bad))
        assert "P5" in out["precision"]["fired"], bad
        assert out["verdict"] == "UNRESOLVED", bad


def test_one_dissenting_draw_of_the_two_hundred_is_enough(tmp_path):
    """§5.4, conformance row L4: "construct a tally set on which exactly one of
    the 200 draws flips iv-c; gate (iv) must come back UNRESOLVED with `P5`
    fired." The counting rule is `dissenting >= 1`, and this is the test that a
    single `k` is not rounded away."""
    verdicts = [False] * ew.UNANIMITY_K
    assert ew.unanimity_fired(verdicts, point_verdict=False) is False
    verdicts[137] = True                       # exactly one dissenter
    assert ew.unanimity_fired(verdicts, point_verdict=False) is True
    # ...and unanimous-but-disagreeing-with-the-point-estimate also fires
    assert ew.unanimity_fired([True] * ew.UNANIMITY_K,
                              point_verdict=False) is True


def test_the_unanimity_rule_propagates_through_the_actual_computation(tmp_path):
    """§5.4: it "does not bound the endpoint by a scale that does not describe
    it; it **propagates the Monte-Carlo uncertainty through the actual
    computation**, re-deriving the interval endpoint 200 times from resampled
    tallies and requiring the verdict itself to be stable."

    Zero-variance tallies give 200 identical verdicts; jittered ones need not,
    and either way the rule reads the verdicts rather than a standard error.
    """
    # Zero-variance tallies: every one of the 200 resampled verdicts is the
    # same, so the rule turns entirely on whether they agree with the POINT
    # verdict — which is what "and with the point-estimate verdict" means.
    # `_mc_cells` gives every treated cell a strictly worse treatment arm, so
    # iv-c's verdict on the resampled tallies is FAIL at every one of the 200.
    cells = [dict(c, season=f"20{19 + i}/2{i}")
             for i, c in enumerate(_mc_cells(n=7, jitter=0))]
    agreeing = ew.unanimity(cells, point_verdict=True)
    assert agreeing["k"] == ew.UNANIMITY_K
    assert agreeing["seed"] == ew.UNANIMITY_SEED
    assert len(agreeing["verdicts"]) == ew.UNANIMITY_K
    assert set(agreeing["verdicts"]) == {True}       # stable under resampling
    assert agreeing["dissenting"] == 0 and agreeing["fired"] is False

    # ...and the same 200 verdicts against the OPPOSITE point verdict fire it,
    # because unanimity is agreement with the point estimate and not merely
    # with each other — the direction §5.4 exists to close is a point estimate
    # that says PASS while the resampled endpoint says FAIL
    disagreeing = ew.unanimity(cells, point_verdict=False)
    assert disagreeing["dissenting"] == ew.UNANIMITY_K
    assert disagreeing["fired"] is True

    # and the whole thing rides on the run's real tallies, through score_table
    path, rows = _run_cells(tmp_path, runner=_table_runner(jitter=0))
    scored = ew.score_table(rows, ledger_path=path)
    u = scored["mc"]["unanimity"]
    assert u["k"] == ew.UNANIMITY_K and u["seed"] == ew.UNANIMITY_SEED
    assert len(u["verdicts"]) == ew.UNANIMITY_K and u["n_mw6_cells"] == 7
    assert u["fired"] is ew.unanimity_fired(
        u["verdicts"], point_verdict=u["point_verdict"])
    assert ew.table_gate(scored)["precision"]["unanimity_dissenting"] == \
        u["dissenting"]


def test_no_deciding_constant_is_overridable_through_any_surface():
    """§2.3, conformance row L18. "**`B = 10,000` is frozen and is not
    overridable.** No CLI flag, keyword or environment variable may pass a
    different `B`, `alpha`, block definition or resampling seed into any
    deciding computation [...] The same closure applies to `n_sims` (20,000),
    `MC_BOOT` (2,000), `SHARDS` (4) and `K` (200, §5.4)."

    v1 left `--n-boot` on the CLI and passed it straight into `score_table`,
    `merge` and `verify` "without refusal".
    """
    corpus, played, ledger = _world()

    # the CLI flag is gone
    assert ew.main(["--n-boot", "500", "--merge"]) == 2

    # ...and the keyword refuses a different value on every deciding surface
    with pytest.raises(ew.EvWidenError) as exc:
        ew.estimand([], n_boot=500)
    assert "not overridable" in str(exc.value)
    for call in (lambda: ew.score_table([], n_boot=500),
                 lambda: ew.score_table([], mc_boot=500),
                 lambda: ew.paired_mc_bootstrap([], n_boot=500),
                 lambda: ew.power_simulation(n_boot=500),
                 lambda: ew.merge(shards=1, n_boot=500),
                 lambda: ew.verify(n_boot=500)):
        with pytest.raises(ew.EvWidenError) as exc:
            call()
        assert "not overridable" in str(exc.value), call


def test_an_unresolved_gate_blocks_adoption_and_can_never_grant_one():
    """§5: "UNRESOLVED blocks adoption and can never grant one." §7.1: it is
    a published VERDICT, not a refusal, and raises nothing."""
    gate = ew.table_gate(_scored(mean_mw6=1e-6, ci=(-1.0, -0.5),
                                 se={"MW6": 1e-5}))
    out = ew.adoption(-0.002, [-0.003, -0.001], [-0.003, -0.001], gate)
    assert out["verdict"].startswith("UNRESOLVED")
    assert "ADOPT" not in out["verdict"].replace("ADOPT is refused", "")


def test_a_missing_monte_carlo_error_is_unresolved_and_never_small():
    """A deciding SE that was never computed is treated as unresolved rather
    than as zero: the direction that cannot be gamed."""
    scored = _scored(mean_mw6=-0.01, ci=(-0.02, -0.005))
    scored["mc"]["mc_se_label"] = {}
    out = ew.table_gate(scored)
    assert out["verdict"] == "UNRESOLVED"
    assert "P1" in out["precision"]["fired"]


def test_score_table_refuses_an_untouched_cell_that_moved(tmp_path):
    path, rows = _run_cells(tmp_path)
    for row in rows:
        if not row["treated_clubs"]:
            row["arms"]["treatment"]["trps"] += 1e-6
            break
    with pytest.raises(ew.TableIdentityBreak):
        ew.score_table(rows, ledger_path=path)


def test_the_hull_analogue_is_printed_with_no_decision_weight(tmp_path):
    """§3.4: "the one Hull-analogue — illustrative, no decision weight"."""
    cells = _cells()
    for cell in cells:
        if cell["season"] == "2019/20" and cell["treated_clubs"]:
            cell["season"] = "2025/26"
    path, rows = _run_cells(tmp_path, cells)
    scored = ew.score_table(rows, ledger_path=path)
    assert scored["hull_analogue"]["club"] == "sunderland"
    # 2025/26's own MW6 cell is treated already (all seven MW6 cells are), and
    # the four renamed 2019/20 cells join it
    assert scored["hull_analogue"]["n_cells"] == 4
    assert "no decision weight" in scored["hull_analogue"]["label"]
    detail = scored["hull_analogue"]["cells"][0]
    assert set(detail["control"]) >= {"p_relegated", "points_mean", "points_p5",
                                      "points_p95"}


def test_the_coverage_reading_direction_is_fixed_before_the_run(tmp_path):
    """§1.3: the counter-hypothesis, with its reading direction pre-stated —
    coverage already at or above nominal that the treatment pushes further above
    is evidence FOR double-counting and AGAINST this rule."""
    path, rows = _run_cells(tmp_path)
    scored = ew.score_table(rows, ledger_path=path)
    reading = scored["coverage_reading"]
    assert "double-counting" in reading and "AGAINST this rule" in reading
    treated = next(c for c in scored["per_cell"] if c["treated_clubs"])
    assert treated["coverage_treated_control"]
    assert treated["coverage_treated_treatment"]


def test_the_table_gate_discloses_that_its_numbers_are_invented():
    """§4.3 as §4.1 reissues it: R1 has no pass rule, so both the tolerance and
    the significance construction are invented, blind, for a SINGLE NAMED
    HORIZON rather than for an average protected code forbids."""
    out = ew.table_gate(_scored())
    assert "invented" in out["disclosure"]
    assert "poor coverage" in out["disclosure"]
    assert "single named horizon" in out["disclosure"]
    assert out["tolerance"] == ew.TABLE_TOLERANCE


def _freeze_cells(path):
    """Re-stamp an audit table ledger as frozen.

    §8.6 removed `run_table`'s `harness_frozen` parameter — the guard
    establishes the state and the row records what it established — so a test of
    what comes AFTER the freeze re-stamps the written rows rather than asking
    the runner to lie about them. This is never a thing the harness itself does.
    """
    rows = [json.loads(l) for l in Path(path).read_text().splitlines()
            if l.strip()]
    for r in rows:
        r["harness_frozen"] = True
    Path(path).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return rows


def test_the_table_ledger_refuses_a_missing_cell(tmp_path):
    """Not a superset, not a subset: a mean over 34 cells is not the quantity
    §4.1 (iv) gates on.

    The short ledger is made by DROPPING a written row, not by running 34
    cells: §3.3's closure 1 now refuses a 34-cell leg before it simulates
    anything, so a truncated run can no longer be the way a truncated ledger
    comes about — which leaves the loader's own completeness check to be tested
    on the thing it actually guards, a ledger that lost a row.
    """
    cells = _cells()
    path, _ = _run_cells(tmp_path, cells)
    rows = _freeze_cells(path)
    path.write_text("\n".join(json.dumps(r) for r in rows[:-1]) + "\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.load_table_ledger(path, expected=cells)
    assert "missing" in str(exc.value)


def test_the_table_ledger_refuses_unfrozen_rows(tmp_path):
    cells = _cells()
    path, _ = _run_cells(tmp_path, cells)
    with pytest.raises(ew.EvWidenError) as exc:
        ew.load_table_ledger(path, expected=cells)
    assert "not a cell of the preregistered run" in str(exc.value)


def test_a_failed_cell_poisons_the_table_ledger(tmp_path):
    path = tmp_path / "table.jsonl"
    cells = _cells()

    def explode(cell, parity_row=None):
        raise RuntimeError("the simulator ran out of memory")

    with pytest.raises(ew.FitFailed):
        ew.run_table(cells, path, runner=explode, parity=_parity_for(cells),
                     config_sha="c", verbose=False)
    assert ew.poison_rows(path)
    with pytest.raises(ew.ShardFailed):
        ew.run_table(cells, path, runner=_table_runner(),
                     parity=_parity_for(cells), config_sha="c", verbose=False)


def test_the_table_leg_never_appends_to_the_protected_retro_ledger():
    """§3.3: `data/epl/sim/retro_r1.jsonl` is read-only and never appended; the
    leg writes its own ledger. §3.3: the parity run is EXECUTED, not read off
    the archive ledger."""
    assert "retro_r1" not in str(ew.TABLE_LEDGER)
    assert ew.paths.rel(ew.TABLE_LEDGER).startswith("data/epl/sim/evwiden")
    assert ew.TABLE_ARM_LABEL == "dc_native"     # what `leaguesim` is told
    assert ew.ARM_NAME == "dc_evwiden"           # what the ledger records
    for target in ew.WRITES:
        assert "retro_r1" not in ew.paths.rel(Path(target))


def test_the_merge_carries_the_table_gate_into_the_adoption_rule(tmp_path):
    _run(tmp_path)
    _freeze_rows(tmp_path)
    passing = {"gate": ew.table_gate(_scored(mean_mw6=-0.001,
                                             ci=(-0.01, -0.0005)))}
    out = _merge(tmp_path, table=passing)
    assert out["adoption"]["conditions"]["iv_table_gate"]["PASS"] is True
    assert not out["adoption"]["verdict"].startswith("INCOMPLETE")


# ==========================================================================
# 12. the evidence contract — §6, and the ultra-review lesson behind it
# ==========================================================================

def test_the_evidence_files_are_written_whichever_way_the_numbers_fall(tmp_path):
    """§4.4: "The result publishes either way… There is no file drawer." And
    ultra-review lesson 1: the verdict's machine-readable basis is COMMITTED,
    not gitignored."""
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, corpus_rows=len(rows))
    _, table_rows = _run_cells(tmp_path)

    out = tmp_path / "evidence"
    written = ew.write_evidence(result, rows, table_rows, directory=out)
    assert set(written) == {"widening.json", "widening_per_fixture.csv",
                            "widening_grid_means.csv",
                            "widening_table_cells.csv", "MANIFEST.sha256"}
    for name in written:
        assert (out / name).exists()


def test_the_verdict_json_carries_r_i6s_frozen_field_list(tmp_path):
    """§9: "the evidence schema, frozen field by field". The superseded table
    said "both CIs" where there are THREE deciding intervals, left the
    820-fixture control without a committed home, promised Sunderland and
    coverage diagnostics no column held, and froze no MANIFEST membership."""
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, corpus_rows=len(rows))
    path, table_rows = _run_cells(tmp_path)
    scored = ew.score_table(table_rows, ledger_path=path)
    gate = ew.table_gate(scored)
    result.update({
        "table": {"scored": scored, "gate": gate},
        "identity_control": {"n_fixtures": 8, "max_abs_diff": 0.0,
                             "mean_abs_diff": 0.0},
        "adoption": ew.adoption(result["mean"], result["ci95"],
                                result["ci95_season"], gate),
        "canaries": {"PASS": True}})
    published = ew.evidence_object(result)

    assert set(published) >= {
        "schema", "generated_at", "prereg_commit", "prereg_blob", "pins",
        "estimand", "ci_week", "ci_season", "ci_table_mw6",
        "gate_i", "gate_ii", "gate_iii", "gate_iv", "controls", "canaries",
        "sequence", "conformance", "grid", "strata", "movement", "coverage",
        "sunderland", "power", "materiality", "verdict"}
    # §9.1: "`conformance` — §8.5's pytest artifact identity: path, SHA-256, the
    # eighteen test ids and the pass count, as the freeze block records them."
    assert set(published["conformance"]) >= {"path", "sha256", "test_ids",
                                             "count", "ok"}
    # §9.1's `pins` carry §0.6's census digest and its 32-cell priceable set,
    # because that census is what scopes this document's table leg
    assert set(published["pins"]) >= {"feasibility_sha256",
                                      "feasibility_priceable"}
    assert published["pins"]["feasibility_sha256"] == ew.FEASIBILITY_SHA256
    assert len(published["pins"]["feasibility_priceable"]) == 32
    # §9.1: "`sequence` — the five markers of §8.4, each with its recorded
    # freeze commit and completion time". v1 had no markers, so no field.
    assert set(published["sequence"]) == set(ew.SEQUENCE_STEPS)
    for step, entry in published["sequence"].items():
        assert set(entry) >= {"present", "freeze_commit", "completed_at",
                              "produced_digest"}, step
    # THREE deciding intervals, each with its own frozen construction
    for name in ("ci_week", "ci_season", "ci_table_mw6"):
        assert set(published[name]) >= {"function", "n_blocks", "B", "alpha",
                                        "seed", "lo", "hi"}
        assert published[name]["function"] == "epl.score.block_bootstrap_ci"
    assert published["ci_table_mw6"]["n_blocks"] == 7
    # the 820-fixture control has a home, with both numbers
    assert set(published["controls"]["identity"]) == {"n", "max_abs_diff",
                                                      "mean_abs_diff", "PASS"}
    assert published["controls"]["table_parity"]["n_cells"] == 32
    # gate (iv) carries §5's precision names, not §9's superseded mc_se_mean
    precision = published["gate_iv"]["precision"]
    assert set(precision) >= {"mc_boot", "mc_seed", "n_particles",
                              "sims_per_particle", "mc_se_mw6", "mc_se_mw0",
                              "mc_se_mw3", "mc_se_mw10", "mc_se_per_cell",
                              "conditions", "resolved"}
    assert "mc_se_mean" not in precision
    # §5.4: "SEVEN entries and only seven [...] There is no `P6` entry and
    # there must not be one: a structural refusal that stops the leg cannot also
    # be a row in a file the stopped leg never writes." v1 froze a field list
    # naming P1-P6 while its harness emitted exactly these seven.
    assert {c["condition"] for c in precision["conditions"]} == {
        "P1", "P2", "P3.MW0", "P3.MW3", "P3.MW10", "P4", "P5"}
    assert len(precision["conditions"]) == 7
    assert "P6" not in json.dumps(precision["conditions"])
    assert "no P6 and there must not be one" in precision["rule"]
    assert set(precision) >= {"unanimity_k", "unanimity_seed",
                              "unanimity_dissenting"}
    assert published["gate_iv"]["mw19"]["decides"] == "nothing"
    assert published["sunderland"]["club"] == "sunderland"
    assert published["materiality"]["required_sentence"] == \
        ew.MATERIALITY_SENTENCE
    assert published["pins"]["realised_config_sha256"] == \
        ew.REALISED_CONFIG_SHA256

    # §6's required publication: the frozen scenarios, the structure, the MDE
    # definition, R, both seeds, the six rows — AND the realised numbers, which
    # decide nothing.
    frozen = {"structure": {"n_thin": 85}, "rows": [],
              "definition": "MDE80", "replicates": 2000,
              "simulation_seed": ew.POWER_SEED,
              "bootstrap": {"seed": ew.BOOTSTRAP_SEED}}
    with_power = ew.evidence_object(result, power=frozen)
    assert with_power["power"]["simulation_seed"] == ew.POWER_SEED
    assert with_power["power"]["bootstrap"]["seed"] == ew.BOOTSTRAP_SEED
    assert with_power["power"]["realised"]["sd_paired_treated"] is not None
    assert with_power["power"]["reproduces"]["PASS"] is False


def test_scored_per_cell_survives_into_the_json_projection(tmp_path):
    """§9.1: "**`scored.per_cell` is not stripped.** The top-level per-cell
    structure must survive into the JSON projection: it is what fills the
    required table-parity and coverage diagnostics, and removing it before
    projection empties fields this contract promises."

    v1's `main` did `{k: v for k, v in scored.items() if k != "per_cell"}`
    before handing the table to `merge`, so `controls.table_parity` and
    `coverage` were published empty on every real run.
    """
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, corpus_rows=len(rows))

    path, cell_rows = _run_cells(tmp_path)
    scored = ew.score_table(cell_rows, ledger_path=path)
    result["table"] = {"scored": scored, "gate": ew.table_gate(scored)}
    published = ew.evidence_object(result)

    assert published["controls"]["table_parity"]["n_cells"] == 32
    assert published["controls"]["table_parity"]["per_cell_digests"]
    assert published["coverage"], "the coverage diagnostic is filled by per_cell"

    # ...and the projection is what `main` hands it: `table_projection` keeps
    # per_cell rather than dropping it
    kept = ew.table_projection(scored, ew.table_gate(scored))
    assert "per_cell" in kept["scored"] and kept["scored"]["per_cell"]


def test_verify_recomputes_the_table_gate_from_the_rebound_tallies(tmp_path):
    """§8.7 and §9.3, conformance row L10: "**`--verify` recomputes the table
    gate from the rebound tallies** — the whole of §5, including the unanimity
    rule — and refuses if the recomputed verdict, the recomputed standard errors
    or the recomputed precision conditions differ from the published ones. A
    verification that re-reads a JSON file it does not re-derive verifies
    nothing."

    v1's `--verify` "does not reproduce the table/MC/adoption decision": it
    averaged one CSV column and compared it with one JSON field.
    """
    path, rows = _run_cells(tmp_path)
    rows = _freeze_cells(path)             # `verify` reads a post-freeze ledger
    scored = ew.score_table(rows, ledger_path=path)
    gate = ew.table_gate(scored)

    _run(tmp_path)
    ledger = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(ledger, corpus_rows=len(ledger))
    result["table"] = ew.table_projection(scored, gate)
    out = tmp_path / "evidence"
    ew.write_evidence(result, ledger, rows, directory=out, manifest=False)

    ok = ew.verify(tmp_path, shards=1, evidence=out / "widening.json",
                   table_ledger=path)
    assert ok["table_gate"]["checked"] is True
    assert ok["table_gate"]["PASS"] is True
    assert ok["table_gate"]["recomputed"]["verdict"] == gate["verdict"]

    # ...and a published verdict that the tallies do not re-derive is refused
    published = json.loads((out / "widening.json").read_text())
    published["gate_iv"]["PASS_or_UNRESOLVED"] = "PASS" \
        if gate["verdict"] != "PASS" else "FAIL"
    (out / "widening.json").write_text(json.dumps(published))
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.verify(tmp_path, shards=1, evidence=out / "widening.json",
                  table_ledger=path)
    assert "table gate" in str(exc.value)


def test_the_manifest_is_the_fifty_two_paths_of_9_3(tmp_path):
    """§9.3's exact list, decidable from the document.

    > The list is decidable from this document: the count is 52, the shard count
    > is fixed at 4, the tally naming function is literal and its 35 members are
    > the product of two enumerated sets, and the five markers are named
    > individually. "Bulky local artifacts" is not a category here; it is a
    > list.

    v1's list was eleven and "substantively incomplete": the deciding tally
    sidecars, `parity.jsonl` and the five sequence markers were all absent, so a
    swapped tally changed no manifested digest.
    """
    assert len(ew.MANIFEST_PATHS) == 49
    assert ew.SHARDS == 4
    assert ew.MANIFEST_PATHS[:4] == (
        "reports/evidence/widening.json",
        "reports/evidence/widening_per_fixture.csv",
        "reports/evidence/widening_table_cells.csv",
        "reports/evidence/widening_grid_means.csv")
    assert ew.MANIFEST_PATHS[4:8] == tuple(
        f"data/epl/fit/evwiden/shard_{i:02d}_of_04.jsonl" for i in range(4))
    assert ew.MANIFEST_PATHS[8:12] == (
        "data/epl/fit/evwiden.json",
        "data/epl/sim/evwiden/table_cells.jsonl",
        "data/epl/fit/evwiden/canary.json",
        "data/epl/sim/evwiden/parity.jsonl")

    tallies = ew.MANIFEST_PATHS[12:44]
    assert len(tallies) == 32
    seasons = ("2019-20", "2020-21", "2021-22", "2022-23", "2023-24",
               "2024-25", "2025-26")
    # §9.3: "the product of two enumerated sets MINUS three cells this document
    # names by key" — §0.6's three, and only those three
    assert set(tallies) == {
        f"data/epl/sim/evwiden/tallies/{s}|{lab}.npz"
        for s in seasons for lab in TABLE_LABELS
        if f"{s.replace('-', '/')}|{lab}" not in ew.EXCLUDED_CELLS}
    # the naming function is literal: what `tally_path` writes is what the
    # MANIFEST names
    assert ew.paths.rel(ew.tally_path(
        ew.TABLE_LEDGER, {"season": "2019/20", "cutoff_label": "MW6"})) in tallies

    assert ew.MANIFEST_PATHS[44:] == tuple(
        f"data/epl/fit/evwiden/sequence/{step}.json"
        for step in ew.SEQUENCE_STEPS)


def test_the_manifest_validates_byte_sizes_and_not_only_digests(tmp_path):
    """§9.3: "Each entry carries a SHA-256 **and a byte size**, and both are
    **validated** on `--verify`, not merely recorded." v1 parsed the sizes and
    never compared them."""
    manifest = tmp_path / "MANIFEST.sha256"
    entries = {}
    for rel in ew.MANIFEST_PATHS:
        target = tmp_path / Path(rel).name
        target.write_text(rel)
        entries[rel] = target
    ew.update_manifest({k: str(v) for k, v in entries.items()}, manifest,
                       require=ew.MANIFEST_PATHS)
    assert ew.assert_manifest_complete(manifest, entries=entries)["PASS"]

    # forge the digest line's SIZE alone: the SHA still agrees, and v1 passed
    text = manifest.read_text().splitlines()
    sha, rel, size = text[0].split()
    text[0] = f"{sha}  {rel}  {int(size) + 1}"
    manifest.write_text("\n".join(text) + "\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.assert_manifest_complete(manifest, entries=entries)
    assert "byte size" in str(exc.value)


def test_the_manifest_is_the_paths_and_a_missing_file_is_a_refusal(
        tmp_path):
    """§9.3: "'Bulky local artifacts' is not a category here; it is a list."
    `--verify` refuses a missing entry, a disagreeing digest, or an entry of
    ours outside the list."""

    manifest = tmp_path / "MANIFEST.sha256"
    entries = {}
    for rel in ew.MANIFEST_PATHS:
        target = tmp_path / Path(rel).name
        target.write_text(rel)
        entries[rel] = target
    ew.update_manifest({k: str(v) for k, v in entries.items()}, manifest,
                       require=ew.MANIFEST_PATHS)
    assert ew.assert_manifest_complete(manifest, entries=entries)["PASS"]

    # a missing promised artifact is a refusal, never a silent omission
    absent = dict(entries)
    absent[ew.MANIFEST_PATHS[-1]] = tmp_path / "nope"
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.update_manifest({k: str(v) for k, v in absent.items()},
                           tmp_path / "other.sha256",
                           require=ew.MANIFEST_PATHS)
    assert "never a silent omission" in str(exc.value)

    # a digest that disagrees is a refusal
    entries[ew.MANIFEST_PATHS[0]].write_text("moved")
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.assert_manifest_complete(manifest, entries=entries)
    assert "digest disagrees" in str(exc.value)


def test_the_manifest_refuses_an_entry_of_ours_outside_the_list(tmp_path):
    manifest = tmp_path / "MANIFEST.sha256"
    entries = {}
    for rel in ew.MANIFEST_PATHS:
        target = tmp_path / Path(rel).name
        target.write_text(rel)
        entries[rel] = target
    ew.update_manifest({k: str(v) for k, v in entries.items()}, manifest)
    manifest.write_text(manifest.read_text()
                        + f"{'0' * 64}  reports/evidence/widening_extra.csv  1\n")
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.assert_manifest_complete(manifest, entries=entries)
    assert "outside the list" in str(exc.value)

    # ...and another experiment's entries are not ours to refuse
    manifest.write_text("\n".join(
        line for line in manifest.read_text().splitlines()
        if "widening_extra" not in line)
        + f"\n{'0' * 64}  reports/evidence/anchoring_per_fixture.csv  1\n")
    assert ew.assert_manifest_complete(manifest, entries=entries)["PASS"]


def test_the_per_fixture_file_reproduces_the_estimand_with_arithmetic_alone(
        tmp_path):
    """`reports/evidence/README.md`'s standard: a reader holding this file and
    nothing else recomputes the headline by averaging one column."""
    import csv as _csv

    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, rows, None, directory=out, manifest=False)

    with (out / "widening_per_fixture.csv").open() as fh:
        got = list(_csv.DictReader(fh))
    assert len(got) == result["n"]
    assert list(got[0]) == list(ew._PER_FIXTURE_COLUMNS)
    assert float(np.mean([float(r["delta"]) for r in got])) == \
        pytest.approx(result["mean"])
    # the block labels are columns, because both bootstraps need them
    assert {"block", "season"} <= set(got[0])
    assert len({r["block"] for r in got}) == result["n_blocks"]
    assert len({r["season"] for r in got}) == result["n_season_blocks"]
    # §2.3: both arms and the corpus, side by side, so a reader can confirm the
    # eight-decimal equality rather than take it
    for row in got:
        assert row["p_home_B"] == row["p_home_corpus"]
        assert float(row["max_abs_dp_vs_corpus"]) == 0.0
        assert float(row["delta"]) == pytest.approx(
            float(row["rps_A"]) - float(row["rps_B"]))
        assert float(row["delta_vs_corpus"]) == pytest.approx(float(row["delta"]))


def test_the_table_evidence_file_carries_both_arms_of_every_cell(tmp_path):
    import csv as _csv

    path, table_rows = _run_cells(tmp_path)
    scored = ew.score_table(table_rows, ledger_path=path)
    out = tmp_path / "evidence"
    ew.write_evidence({"schema": ew.SCHEMA_ID,
                       "table": {"scored": scored}}, None, table_rows,
                      directory=out, manifest=False)
    with (out / "widening_table_cells.csv").open() as fh:
        got = list(_csv.DictReader(fh))
    # §9.2: 32 rows — one per priceable CELL, the paired shape the deltas have
    assert len(got) == len(table_rows) == 32
    assert list(got[0]) == list(ew._TABLE_COLUMNS)
    treated = [r for r in got if r["treated_clubs"]]
    assert len(treated) == 15
    for row in treated:
        assert row["sampler_digest_control"] != row["sampler_digest_treatment"]
        assert row["parity_digest_simretro"]
        assert row["provisional_control"] and row["provisional_treatment"]
        assert row["mc_se_paired"] != ""
    assert all(float(r["delta_trps"]) == 0.0 for r in got
               if not r["treated_clubs"])


def test_the_grid_file_carries_every_point_including_the_degenerate_ones(
        tmp_path):
    import csv as _csv

    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, None, None, directory=out, manifest=False)
    with (out / "widening_grid_means.csv").open() as fh:
        got = list(_csv.DictReader(fh))
    assert list(got[0]) == ["e_star", "n_thin", "n_treated", "mean_delta",
                            "ci_lo", "ci_hi", "n_blocks", "degenerate",
                            "decides"]
    assert {float(r["e_star"]) for r in got} == {1.0, 3.0, 5.0, 8.0, 10.0, 12.0}
    degenerate = {float(r["e_star"]) for r in got if r["degenerate"] == "True"}
    assert set(ew.E_GRID_DEGENERATE) <= degenerate
    assert {r["decides"] for r in got} == {"nothing"}


def test_the_manifest_updates_in_place_and_keeps_what_it_did_not_write(tmp_path):
    """The manifest is a shared file two earlier experiments already wrote;
    rewriting it from scratch would silently drop their entries."""
    path = tmp_path / "MANIFEST.sha256"
    path.write_text("aaa  data/epl/fit/freshness.json  10\n"
                    "bbb  data/epl/fit/anchoring.json  20\n")
    target = tmp_path / "thing.json"
    target.write_text("{}")
    ew.update_manifest({"data/epl/fit/evwiden.json": target}, path)
    lines = path.read_text().splitlines()
    assert any(l.startswith("aaa ") for l in lines)
    assert any(l.startswith("bbb ") for l in lines)
    entry = next(l for l in lines if "evwiden.json" in l)
    digest, name, size = entry.split()
    assert digest == ew.sha256_file(target)
    assert int(size) == target.stat().st_size

    target.write_text("{ }")             # a rewrite updates in place, not appends
    ew.update_manifest({"data/epl/fit/evwiden.json": target}, path)
    assert sum(1 for l in path.read_text().splitlines()
               if "evwiden.json" in l) == 1


# ==========================================================================
# 13. the §6 freeze — the commit that makes "the design was fixed first" checkable
# ==========================================================================

def test_no_public_fit_surface_accepts_a_freeze_state_boolean():
    """§8.6, conformance row L7. "**No public fit surface accepts a freeze-state
    boolean.** `Engine`, `TableRunner`, `ParityRunner`, `run_fits` and
    `run_table` carry no `harness_frozen` parameter, and no other entry point
    may introduce one."

    v1's CLI obtained live freeze state and then handed it to five surfaces that
    took the caller's word for it — and `assert_may_fit` performed NO Git
    verification when the word was `True`. A direct harness call could therefore
    fit the pinned artifacts while unfrozen, which is the whole of what
    "anywhere" forbids. A guard that trusts a caller-supplied `True` performs no
    verification at exactly the moment verification matters.
    """
    import inspect

    surfaces = (ew.Engine.__init__, ew.TableRunner.__init__,
                ew.ParityRunner.__init__, ew.run_fits, ew.run_table,
                ew.assert_may_fit, ew.run_parity_oracle)
    for fn in surfaces:
        params = set(inspect.signature(fn).parameters)
        assert "harness_frozen" not in params, fn
        # and no synonym smuggles it back in
        assert not {p for p in params
                    if "frozen" in p or "freeze" in p}, (fn, params)


def test_the_pre_freeze_guard_is_keyed_to_the_artifacts_not_the_directory():
    """R2's binding obligation, and the sentence it withdrew as FALSE: "the
    harness's own guards refuse to produce [a delta] until the freeze block is
    committed."

    `_guard_ledger_location` is keyed to the run DIRECTORY, so a `--run` or
    `--table` pointed at a `--dir` outside the default directories could fit the
    real archive and produce a real delta with no freeze block anywhere, and
    `data/` is gitignored so it would leave no Git trace. The repaired guard is
    keyed to the freeze state and to the ARTIFACT IDENTITY being read.
    """
    corpus, played, _ = _world()
    # a synthetic world fits freely, before the freeze and after
    assert ew.assert_may_fit("test", played=played,
                             corpus=corpus)["real_artifacts"] is False
    # a caller that has not loaded a frame is a caller about to load the pinned
    # one, and is refused
    with pytest.raises(ew.EvWidenError) as exc:
        ew.assert_may_fit("test", played=None)
    assert "about to be loaded" in str(exc.value)
    assert "never to the output directory" in str(exc.value)


@pinned
def test_no_scratch_directory_lets_the_pinned_archive_be_fitted_unfrozen(
        tmp_path, real):
    """The hole R2 names at `epl/evwiden.py:1712-1740,4158-4189`, closed: no
    `--dir` moves the refusal, because the refusal never read the directory."""
    corpus, played, ledger = real
    assert ew.is_pinned_archive(played) is True
    assert ew.is_pinned_corpus(corpus) is True

    for kwargs in ({"played": played}, {"corpus": corpus},
                   {"played": played, "corpus": corpus}):
        with pytest.raises(ew.EvWidenError) as exc:
            ew.assert_may_fit("test", directory=tmp_path, **kwargs)
        assert "IS the pinned" in str(exc.value)

    # ...and the Engine refuses at construction, before it spends a store
    with pytest.raises(ew.EvWidenError):
        ew.Engine(corpus, played, ledger=ledger, directory=tmp_path)


@pinned
def test_the_table_runners_refuse_the_pinned_archive_before_the_freeze(tmp_path):
    """`--table` had the analogous directory-keyed hole, and both the new runner
    and the parity oracle's protected runner are gated now."""
    from epl import baseline

    matches = baseline.load_matches()
    with pytest.raises(ew.EvWidenError):
        ew.TableRunner(matches, directory=tmp_path)
    with pytest.raises(ew.EvWidenError):
        ew.ParityRunner(matches, directory=tmp_path)


def test_the_parity_runner_re_establishes_the_permit_at_every_cell(monkeypatch):
    """The adjudication of 2026-08-29, F8 (IMP-POST-FIT-PROSE, cache half).
    "`ParityRunner.__init__` caches `assert_may_fit` once, and one instance
    executes all 32 cells without rereading the current document, witness, or
    record. That contradicts the every-fit promise."

    §8.6 asks the permit at the moment the sampler runs, "not only at
    construction: the freeze state and the first-real-fit regime are properties
    of the moment the sampler runs, and a long run must not carry a stale
    verdict." One construction and thirty-two protected ADVI fits is exactly the
    long run the clause is about.
    """
    import pandas as pd

    permits = {"n": 0, "raise_from": None}

    def gate(where, **kw):
        permits["n"] += 1
        if permits["raise_from"] is not None and \
                permits["n"] >= permits["raise_from"]:
            raise ew.FreezeStateUnverified("the document moved under the run")
        return {"frozen": False, "real_artifacts": False, "where": where}

    monkeypatch.setattr(ew, "assert_may_fit", gate)

    class _Runner:
        def __call__(self, **kw):
            raise AssertionError("the permit must be asked BEFORE the runner")

    from epl import simretro
    monkeypatch.setattr(simretro, "ArchiveRunner",
                        lambda *a, **kw: _Runner())
    frame = pd.DataFrame({"season": [], "home_key": [], "away_key": [],
                          "played": []})
    runner = ew.ParityRunner(frame, verbose=False, directory=ew.NO_TARGET)
    assert permits["n"] == 1                       # construction asked once

    cell = {"season": "2019/20", "cutoff_label": "MW6", "cutoff": "2019-09-28"}
    permits["raise_from"] = 2
    with pytest.raises(ew.FreezeStateUnverified):
        runner(cell)
    assert permits["n"] == 2, "the call re-asked rather than reading a cache"
    # ...and it is not a stored verdict the constructor left behind
    assert not hasattr(runner, "may_fit")
    assert "_permit" in ew._calls_made(ew.ParityRunner.__call__)
    assert "assert_may_fit" in ew._calls_made(ew.ParityRunner._permit)


def test_the_freeze_block_enumerates_six_passes_and_one_prior_history_entry():
    """v3 §8.2's SIX passes, "authorised for this document, prospectively" —
    and the seventh, "prior history and enumerated as such".

    > **The seventh pass is prior history and is enumerated as such.** v2's
    > §8.2 pass 7 [...] is not authorised here, because it is not repeatable
    > here [...] The freeze block enumerates it in a HISTORY section, distinct
    > from the six above [...] so that the enumeration stays complete without
    > pretending the pass was v3's to authorise.
    """
    assert len(ew.PRE_FREEZE_RUNS) == 6
    joined = " ".join(ew.PRE_FREEZE_RUNS)
    for marker in ("--membership", "--plan", "--canary --no-results-canary",
                   "pytest epl/tests/test_evwiden.py", "dcfit.fit_epl",
                   "--partial-engine", "--freeze-block", "--power"):
        assert marker in joined, marker
    assert "TemporaryDirectory" in joined and "paths.STORE_DIR" in joined
    # ALL SIX are read-only: v3 authorises no pass that fits or simulates
    assert "feasibility" not in joined.lower()
    assert "quarantine" not in joined.lower()
    # ...and the seventh is HISTORY, in its own list, with its census
    assert len(ew.PRIOR_PASSES) == 1
    history = ew.PRIOR_PASSES[0]
    for marker in ("v2 §8.2 pass 7", "2026-08-28", "9adc3bc", "dc_native",
                   "32 priceable", "excluded_mass_ceiling",
                   "man_city v sheffield_united", "0.0234",
                   "man_city v leeds", "0.0216",
                   "man_city v luton", "0.0328", "read-only"):
        assert marker in history, marker
    assert "repair round" not in joined
    # ...and pass 4 is now a COMMAND rather than a description of one no
    # command could run (the review's NEW-B5)
    assert any("--partial-engine" in run for run in ew.PRE_FREEZE_RUNS)


@pinned
def test_membership_and_plan_carry_the_table_cell_memberships(tmp_path, real):
    """§8.2 pass 1 authorises `--membership` and `--plan` to compute "§2.2's
    cells, §2.3's population, §3.3's TABLE CELLS and the digests the freeze
    commit records". The table cells were the half the CLI omitted."""
    corpus, played, ledger = real
    cells = ew.default_table_cells(played)
    assert len(cells) == ew.EXPECTED_TABLE_CELLS

    digests = ew.membership_digests(corpus, played, ledger, table=cells)
    assert {"table_treated", "table_untouched"} <= set(digests["digests"])
    assert digests["counts"]["table_treated"] == ew.EXPECTED_TABLE_TREATED
    assert digests["counts"]["table_untouched"] == ew.EXPECTED_TABLE_UNTOUCHED

    plan = ew._plan(corpus, played, ledger, ew.SHARDS, tmp_path, table=cells)
    assert {"table_treated", "table_untouched"} <= set(plan["digests"])
    assert plan["budget"]["table_fits"] == 64
    assert plan["budget"]["table_simulations"] == 96
    # v3 §2.4's POST-FREEZE budget is **147 fits**: the four results-canary
    # fits and the single-opening exercise "are counted because they are real
    # fits on the real archive: §8.4 makes them the first two steps of the
    # frozen sequence, and a budget that omits them would understate both the
    # clock and the moment §8.7's regime comes into force". The census took the
    # table leg from 35 cells to 32, so the two table legs are 64 fits and 96
    # simulations rather than 70 and 105.
    assert plan["budget"]["canary_fits"] == 4
    assert plan["budget"]["single_opening_fits"] == 1
    assert plan["budget"]["total_fits"] == 147 == 4 + 1 + 78 + 64
    # ...and §2.4 states the WHOLE-LIFECYCLE figure too, which v2's did not:
    # v2 §8.2 pass 7 spent 35 real fits and 35 real simulations before this
    # document existed, and the review's P5-I1 found v2 calling 153/105 the
    # "whole experiment" while they sat outside it.
    assert plan["budget"]["prior_history_fits"] == 35
    assert plan["budget"]["prior_history_simulations"] == 35
    assert plan["budget"]["lifecycle_fits"] == 182 == 147 + 35
    assert plan["budget"]["lifecycle_simulations"] == 131 == 96 + 35
    assert "~4 hours" in plan["budget"]["bound"]


def test_the_freeze_refuses_until_the_hash_table_lands():
    """No freeze block is committed, so §8.6's state is not established."""
    status = ew.harness_freeze_status()
    assert status["frozen"] is False
    assert "has not landed" in status["why"]
    with pytest.raises(ew.EvWidenError) as exc:
        ew.require_harness_freeze()
    assert "SYNTHETIC" in str(exc.value)


def test_the_freeze_state_is_read_out_of_v2_and_out_of_nothing_else(tmp_path):
    """§8.6 condition (1): "`reports/epl_widening_prereg_v2.md` [...] this file
    and no other. No second source is accepted."

    The in-tree audit's finding 10 and the review's N-FREEZE-COMMIT: the guard
    "still accepts arbitrary `sources` and `rev`", so a caller could choose which
    blob the freeze state is read out of — and `merge`'s `freeze_sources`
    forwards straight into it. The keyword survives; a different value does not.
    """
    other = tmp_path / "prereg.md"
    other.write_text("| `epl/evwiden.py` | " + "0" * 64 + " |\n")
    for call in (lambda: ew.harness_freeze_status([other]),
                 lambda: ew.harness_freeze_status([ew.AMENDMENTS_PATH]),
                 lambda: ew.harness_freeze_status([ew.PREREG_V1_PATH]),
                 lambda: ew.require_harness_freeze([other]),
                 lambda: ew.harness_freeze_status([ew.PREREG_PATH, other])):
        with pytest.raises(ew.EvWidenError) as exc:
            call()
        assert "this file and no other" in str(exc.value)
    # ...and a caller-selected revision answers a question about another tree
    with pytest.raises(ew.EvWidenError) as exc:
        ew.harness_freeze_status(rev="HEAD~1")
    assert "at no other " in str(exc.value)
    # the ONE permitted value is the file the law names, and it behaves as the
    # default does
    assert (ew.harness_freeze_status([ew.PREREG_PATH])["frozen"]
            is ew.harness_freeze_status()["frozen"])


def test_an_uncommitted_hash_paste_freezes_nothing(monkeypatch):
    """R2, the defect that replaces v1's round-trip test: "v1's
    freeze guard parses current prose against current filesystem bytes, which an
    uncommitted two-line paste satisfies; that is not a freeze and this document
    does not accept it as one."

    A paste carrying the CORRECT digests of the harness files on disk is
    exactly what v1's guard called frozen. There is no longer any second file to
    put one in — §8.6 condition (1) names one source and the guard now refuses
    every other — so what is asserted is the same fact at that one source: while
    its committed blob is absent, nothing about the working tree freezes it."""
    monkeypatch.setattr(ew, "git_committed_bytes",
                        lambda relpath, rev="HEAD": None)
    status = ew.harness_freeze_status()
    assert status["frozen"] is False
    assert status["files"] == {}
    assert "COMMITTED" in status["why"]
    assert status["uncommitted_sources"] == [ew.paths.rel(ew.PREREG_PATH)]


def test_the_freeze_reads_the_committed_prose_and_the_committed_bytes():
    """R2: the guard verifies "the Git object identity of the prereg blob whose
    hash table it reads". Both sides come out of Git — the prose AND the harness
    bytes — and the working tree is checked as well, so a dirty tree is not
    frozen either."""
    status = ew.harness_freeze_status()
    assert status["rev"] == "HEAD"
    # §8.6 condition (1) names ONE file. The superseded guard also accepted
    # `reports/epl_sim_amendments.md` as a freeze source and then checked the
    # commit-and-ancestry condition against whichever file carried the hash
    # table, which is not the file the law names — and §8.3 expressly forbids
    # appending an amendment-ledger cross-reference for this document.
    assert [s["path"] for s in status["sources"]] == [
        ew.paths.rel(ew.PREREG_PATH)]
    assert all(s["committed"] for s in status["sources"])
    assert all(s["blob"] for s in status["sources"])
    # the prereg is committed and the harness hash table has NOT been pasted:
    # §3.3(1) reaffirms that the freeze stays unpasted until the harness
    # implements the law
    assert status["frozen"] is False
    assert status["missing"] == list(ew.HARNESS_FILES)


def _as_if_committed(table: str | None = None, *, monkeypatch=None):
    """`git show` as it would read after the freeze commit landed.

    The prereg carries `table` (the rendered hash table by default) and every
    harness file's committed bytes are the working tree's, which is what a clean
    tree at the freeze commit looks like.

    **And the working tree carries the same bytes**, because §8.6 condition
    (1) now binds the document's CURRENT bytes to its committed blob
    (IMP-POST-FIT-PROSE) and a real freeze commit leaves the two equal — the
    block is appended to the file and then committed. A simulation in which
    they differ is simulating the uncommitted-edit state the condition exists
    to catch, not a landed freeze. Pass `monkeypatch` to have
    :func:`ew.working_tree_bytes` mocked alongside `git show`; the callers that
    are testing an unfrozen state may omit it.
    """
    text = table if table is not None else "\n".join(
        f"| `{name}` | {ew.sha256_file(ew.paths.REPO_ROOT / name)} |"
        for name in ew.HARNESS_FILES) + "\n"

    def in_tree(relpath):
        if relpath == ew.paths.rel(ew.PREREG_PATH):
            return text.encode()
        return (ew.paths.REPO_ROOT / relpath).read_bytes()

    if monkeypatch is not None:
        monkeypatch.setattr(ew, "working_tree_bytes", in_tree)

    def committed(relpath, rev="HEAD"):
        if relpath == ew.paths.rel(ew.PREREG_PATH):
            return text.encode()
        if relpath in ew.HARNESS_FILES:
            return (ew.paths.REPO_ROOT / relpath).read_bytes()
        return b""

    return committed


@pytest.fixture
def unrun_feasibility(tmp_path, monkeypatch):
    """The state §8.3's block renderer can be exercised in, after pass 7 ran.

    §8.2 pass 7 RAN in this repository on 2026-08-28 and its census carries
    three unpriceable cells, so `freeze_block` refuses in this checkout — by
    design, and `test_the_freeze_block_refuses_over_a_census_that_answered_the_
    question` is where that refusal is asserted, over every state of the record.
    The obligations §8.3 puts on the block's CONTENTS are separate obligations
    and still have to be executable; they are executable only in the state the
    renderer was written for, which §8.2 describes: "while it does not exist the
    enumeration says the pass has not been run", and nothing is refused for it.

    So these tests render the block over an ABSENT record. What they may not do
    is render it over a record that says the census passed — that would be a
    test asserting a lifecycle state no run produced, which is the class §8.6
    exists to refuse.
    """
    record = tmp_path / "evwiden_parity_feasibility.json"
    record.write_text(json.dumps(_census_record(), indent=2))
    raw = record.read_bytes()
    monkeypatch.setattr(ew, "FEASIBILITY_RECORD", record)
    monkeypatch.setattr(ew, "FEASIBILITY_SHA256",
                        __import__("hashlib").sha256(raw).hexdigest())
    monkeypatch.setattr(ew, "FEASIBILITY_BYTES", len(raw))
    assert ew.feasibility_status()["ok"] is True

    # ...and §8.5's artifact, which the block also refuses to render without.
    # It is DERIVED from running the eighteen scenarios here rather than
    # planted: the outcomes it records are the outcomes those rows actually
    # reached in this process, which is the same computation the eighteen
    # committed tests perform. A fixture that wrote "passed" without running
    # them would be asserting a lifecycle state no run produced — the class
    # §8.6 refuses, and the reason this fixture does not fabricate a passing
    # census either.
    monkeypatch.setattr(ew, "CONFORMANCE_ARTIFACT",
                        tmp_path / "evwiden_conformance.json")
    ew.write_conformance_artifact(
        {rid: ("passed" if ew.conformance_row(rid)["ok"] else "failed")
         for rid in ew.CONFORMANCE_ROWS})
    assert ew.conformance_artifact_status()["ok"] is True
    return tmp_path


@pinned
def test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head(
        monkeypatch, unrun_feasibility):
    """§8.6's task for the guard: verify a COMMITTED freeze — the Git identity
    of the source, not prose beside bytes.

    The mocked committed source is now the harness's OWN rendered freeze block,
    because §8.6 conditions (3) and (4) read the schema identifier and the
    membership digests out of it. That is why this test reads the pinned
    artifacts: a two-hash-line stand-in is no longer a freeze, and v1's test
    accepted one.
    """
    block = ew.freeze_block()
    monkeypatch.setattr(ew, "git_committed_bytes",
                        _as_if_committed(block, monkeypatch=monkeypatch))
    status = ew.harness_freeze_status()
    assert status["frozen"] is True
    assert status["is_ancestor"] is True
    assert ew.git_is_ancestor(status["commit"]) is True
    assert all(f["match"] for f in status["files"].values())
    assert all(f["committed"] == f["actual"] for f in status["files"].values())

    # ...and a commit that is not an ancestor of HEAD freezes nothing
    monkeypatch.setattr(ew, "git_is_ancestor", lambda *a, **k: False)
    later = ew.harness_freeze_status()
    assert later["frozen"] is False
    assert "not an ancestor" in later["why"]


def test_the_freeze_refuses_a_hash_that_no_longer_describes_the_file(monkeypatch):
    """§8.3 step 2: "if any hash differs at the time the run is executed, it is
    not the run this document preregisters"."""
    monkeypatch.setattr(ew, "git_committed_bytes", _as_if_committed(
        "\n".join(f"| `{name}` | {'0' * 64} |"
                  for name in ew.HARNESS_FILES) + "\n"))
    status = ew.harness_freeze_status()
    assert status["frozen"] is False
    assert "differs from the committed bytes" in status["why"]


def test_a_dirty_working_tree_is_not_a_frozen_harness(monkeypatch):
    """The recorded digest must describe BOTH the committed bytes and the file
    the run will actually import."""
    monkeypatch.setattr(
        ew, "git_committed_bytes",
        lambda relpath, rev="HEAD": (
            ("\n".join(f"| `{name}` | {'a' * 64} |"
                       for name in ew.HARNESS_FILES) + "\n").encode()
            if relpath == ew.paths.rel(ew.PREREG_PATH) else b"different bytes"))
    status = ew.harness_freeze_status()
    assert status["frozen"] is False
    for rec in status["files"].values():
        assert rec["match"] is False


def test_the_first_fit_record_lives_at_one_fixed_repo_root_keyed_path():
    """§8.6, conformance row L8. "The record lives at **one fixed
    repo-root-keyed path**, `data/epl/fit/evwiden_first_real_fit.json`, derived
    from `paths.REPO_ROOT` and from nothing else. **No function that reads or
    writes it takes a directory argument.**"

    v1's record was written below the caller's chosen directory, so a fresh or
    deleted `--dir` reset the entire §8.7 regime — the one-way ratchet had a way
    back.
    """
    import inspect

    assert ew.FIRST_FIT_JSON == (ew.paths.REPO_ROOT / "data" / "epl" / "fit"
                                 / "evwiden_first_real_fit.json")
    for fn in (ew.first_fit_record, ew.record_first_real_fit,
               ew.assert_no_hashed_file_moved):
        params = set(inspect.signature(fn).parameters)
        assert not {p for p in params if "dir" in p or "path" in p}, (fn, params)


def test_the_first_real_fit_event_is_recorded_once_and_then_binds(tmp_path,
                                                                  monkeypatch):
    """§8.7, made mechanical: from the moment a real fit on the real archive
    exists, ANY change to ANY hashed file invalidates this preregistration — no
    note, no dated appendix, no disclosure and no owner ruling restores it.

    The record is repo-root-keyed, so the test moves the repo root rather than
    passing a directory the harness no longer accepts.
    """
    monkeypatch.setattr(ew, "FIRST_FIT_JSON", tmp_path / "first_real_fit.json")
    # §8.6's two artifacts are ONE mechanism: pointing the record away and
    # leaving the witness at its real path writes into the preregistered tree
    monkeypatch.setattr(ew, "FIRST_FIT_WITNESS",
                        tmp_path / "first_fit_witness.jsonl")
    assert ew.first_fit_record() is None
    record = ew.record_first_real_fit(where="the results canary")
    assert record["where"] == "the results canary"
    assert set(record["harness"]) == set(ew.HARNESS_FILES)
    assert record["commit"] and record["prereg_blob"]
    assert record["prereg"] == ew.paths.rel(ew.PREREG_PATH)
    # written once and never rewritten
    again = ew.record_first_real_fit(where="something else")
    assert again["at"] == record["at"] and again["where"] == record["where"]

    ew.assert_no_hashed_file_moved()                  # nothing moved yet
    moved = json.loads((tmp_path / "first_real_fit.json").read_text())
    moved["harness"][ew.HARNESS_FILES[0]] = "0" * 64
    (tmp_path / "first_real_fit.json").write_text(json.dumps(moved))
    with pytest.raises(ew.FreezeStateUnverified) as exc:
        ew.assert_no_hashed_file_moved()
    assert "INVALIDATES this preregistration" in str(exc.value)


def test_a_first_fit_record_naming_another_prereg_blob_is_unverified(
        tmp_path, monkeypatch):
    """§8.6: "On every later fit the guard re-reads it and raises
    `FreezeStateUnverified` if the recorded prereg blob is not the blob of the
    freeze commit."

    A record carried over from another document — v1's, say — would otherwise
    let this run inherit a first-fit event that belongs to a preregistration
    that decides nothing.
    """
    monkeypatch.setattr(ew, "FIRST_FIT_JSON", tmp_path / "first_real_fit.json")
    # §8.6's two artifacts are ONE mechanism: pointing the record away and
    # leaving the witness at its real path writes into the preregistered tree
    monkeypatch.setattr(ew, "FIRST_FIT_WITNESS",
                        tmp_path / "first_fit_witness.jsonl")
    ew.record_first_real_fit(where="the results canary")
    planted = json.loads((tmp_path / "first_real_fit.json").read_text())
    planted["prereg_blob"] = "0" * 40
    (tmp_path / "first_real_fit.json").write_text(json.dumps(planted))
    with pytest.raises(ew.FreezeStateUnverified) as exc:
        ew.assert_no_hashed_file_moved()
    assert "prereg blob" in str(exc.value)


def test_the_freeze_guard_checks_the_schema_and_the_membership_digests(
        monkeypatch, tmp_path):
    """§8.6's four conditions, and v1's guard parsed only the first two.

    "Parsing two hash lines out of current prose is not a freeze"; nor is
    parsing two hash lines out of committed prose. The block must also carry the
    schema identifier `epl-evwiden-2` and membership digests that equal a fresh
    recomputation from the pinned artifacts. A mocked source containing only two
    hash lines is not frozen, and v1's test accepted one that was.
    """
    monkeypatch.setattr(ew, "git_committed_bytes",
                        _as_if_committed(monkeypatch=monkeypatch))
    status = ew.harness_freeze_status()
    assert status["frozen"] is False
    assert "schema" in status["why"] or "membership" in status["why"]
    assert status["schema_ok"] is False


# ==========================================================================
# 14. the detached launch — §2.4, generated rather than committed
# ==========================================================================

def test_the_launcher_is_generated_and_lives_in_the_run_directory(monkeypatch,
                                                                  tmp_path):
    """§8.3 names two harness files. A loose `run_evwiden.sh` would be code whose
    bytes nothing hashes while being able to change which shards run.

    v3 §8.2 gives it ONE target and one moment: the preregistered run directory,
    after the freeze. Both are simulated here, because the launcher is a
    post-freeze artifact and this test is about where it lands."""
    monkeypatch.setattr(ew, "_frozen_now", lambda: True)
    monkeypatch.setattr(ew, "EVWIDEN_DIR", tmp_path)
    path = ew.write_launch_script(tmp_path)
    assert path.parent == tmp_path
    assert path.name == ew.LAUNCH_NAME
    assert not str(path).startswith(str(ew.paths.REPO_ROOT / "scripts"))
    assert path.stat().st_mode & 0o111        # executable
    assert not (ew.paths.REPO_ROOT / "epl" / "run_evwiden.sh").exists()
    # ...and nowhere else, even after the freeze
    with pytest.raises(ew.EvWidenError) as exc:
        ew.write_launch_script(tmp_path / "elsewhere")
    assert "one target" in str(exc.value)


def test_the_launcher_pins_blas_before_python_and_runs_unbuffered(tmp_path):
    text = ew.launch_script(tmp_path)
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert f"export {var}=1" in text or f"{var}=1" in text
    assert text.index("export OMP_NUM_THREADS") < text.index("$PY -u -m epl.evwiden")
    assert "-u -m epl.evwiden" in text
    assert "nohup sh" in text                 # the launch line, in a comment
    assert "<<" not in text                   # never a stdin heredoc


def test_the_launcher_runs_shards_sequentially_and_waits_per_pid(tmp_path):
    """§2.4: parallel shards crash on the featpanel `.tmp` rename race, and a
    bare `wait` returns the LAST job's status — a failed shard would sail past."""
    text = ew.launch_script(tmp_path)
    order = [text.index(f"--shard {i}/4") for i in range(4)]
    assert order == sorted(order)
    assert 'wait "$pid"' in text
    for line in text.splitlines():
        assert line.strip() != "wait"
    assert text.count("run_step shard_") == 4
    assert "exit 2" in text                   # a failed step stops the run


def test_the_launcher_emits_exactly_the_five_steps_in_order(tmp_path):
    """§8.4, conformance row L9: "**`launch.sh` must emit exactly this order.**
    v1's launcher ran canary → shards → table → merge, with no step-2 marker,
    and would have re-run the once-only canary after a manual step 2. A
    committed test asserts that the generated script's step order equals the
    five above, that each step's precondition check appears before its command,
    and that removing any marker makes the corresponding step refuse."

    The last of the three is `test_a_step_without_its_predecessors_marker_refuses`;
    the first two are here.
    """
    text = ew.launch_script(tmp_path)
    assert ew.RUN_ORDER == ("canary", "single_opening", "shards", "merge",
                            "parity_and_table")

    # step 1 the canary, step 2 the single opening (by HAND, into a scratch
    # directory), step 3 the four shards, step 4 the merge, step 5 the parity
    # oracle and then the table. v1 ran table BEFORE merge and had no step 2.
    at = [text.index(m) for m in
          ("# STEP 1", "# STEP 2", "# STEP 3", "# STEP 4", "# STEP 5")]
    assert at == sorted(at), at
    assert text.index("run_step canary") < text.index("run_step shard_00")
    assert text.index("run_step shard_03") < text.index("run_step merge")
    assert text.index("run_step merge") < text.index("run_step table")

    # Each step's precondition check appears BEFORE its command — AS A
    # COMMAND. The in-tree audit found this obligation unenforced: every
    # `need_marker` line could be deleted and the committed test stayed green,
    # because the marker's NAME also appears in the `#   marker:
    # sequence/stepN_*.json` comment inside the preceding block, so an index
    # comparison over the whole text held vacuously. Comments are dropped here.
    commands = [line for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    for step, command in (("step1_results_canary", "run_step shard_00"),
                          ("step2_single_opening", "run_step shard_00"),
                          ("step3_shards", "run_step merge"),
                          ("step4_merge", "run_step table"),
                          ("step5_parity", "run_step evidence")):
        guards = [i for i, line in enumerate(commands)
                  if line.startswith(f"need_marker {step} ")]
        assert len(guards) == 1, (step, guards)
        at = [i for i, line in enumerate(commands)
              if line.startswith(command)]
        assert at and guards[0] < at[0], step
    # ...and there are exactly five of them, so deleting one is visible here
    assert sum(1 for line in commands
               if line.startswith("need_marker ")) == 5


def test_the_launcher_publishes_the_evidence_after_the_table_leg(tmp_path):
    """§8.4 puts the merge at step 4 and the parity oracle and table at step 5,
    and §9 requires the evidence files to carry gate (iv).

    A launcher that writes the evidence inside step 4 publishes a verdict with
    no table gate in it and then runs the four-hour leg that decides half of
    the adoption rule — and never publishes what it found. The merge's own
    product, `data/epl/fit/evwiden.json`, is step 4's; the §9 evidence is
    written by a final pass once step 5's marker exists.
    """
    text = ew.launch_script(tmp_path)
    step4 = text.index("# STEP 4")
    step5 = text.index("# STEP 5")
    # step 4 merges and does NOT publish
    merge_line = text.index("run_step merge ")
    assert step4 < merge_line < step5
    assert "--evidence" not in text[step4:step5]
    # ...and the evidence pass comes after step 5's marker
    evidence_line = text.index("--evidence")
    assert evidence_line > text.index("run_step table ")
    assert text.index("need_marker step5_parity") < evidence_line


def test_the_launcher_generates_four_shards_and_refuses_any_other_count(
        tmp_path):
    """§8.4: "**`SHARDS = 4` is enforced, not defaulted.** `--shards` may not be
    passed a different value: the CLI refuses it, the launcher generates four,
    and the MANIFEST's shard filenames are the four of §9.3."
    """
    assert ew.SHARDS == 4
    text = ew.launch_script(tmp_path)
    assert text.count("run_step shard_") == 4
    for i in range(4):
        assert f"--shard {i}/4" in text
    with pytest.raises(ew.EvWidenError) as exc:
        ew.launch_script(tmp_path, shards=2)
    assert "not the run this document preregisters" in str(exc.value)
    assert ew.main(["--shards", "2", "--merge"]) == 2


def test_the_frozen_sequence_is_five_markers_at_one_fixed_location():
    """§8.4: "Markers live at one fixed location,
    `data/epl/fit/evwiden/sequence/`, one JSON file per step."
    """
    assert ew.SEQUENCE_STEPS == ("step1_results_canary", "step2_single_opening",
                                 "step3_shards", "step4_merge", "step5_parity")
    assert ew.SEQUENCE_DIR == ew.EVWIDEN_DIR / "sequence"
    for step in ew.SEQUENCE_STEPS:
        assert ew.sequence_marker_path(step).parent == ew.SEQUENCE_DIR


def test_a_step_without_its_predecessors_marker_refuses(tmp_path, monkeypatch):
    """§8.4: "Each step **refuses unless its predecessor's completion marker
    exists**; the refusal is `SequenceViolation`."

    v1 had no markers at all: `require_run_preconditions` checked only the
    canary, so a merge could run without shards and a table could run before a
    merge — and the launcher did exactly that.
    """
    monkeypatch.setattr(ew, "SEQUENCE_DIR", tmp_path / "sequence")
    monkeypatch.setattr(ew, "git_head", lambda rev="HEAD": "deadbeef")

    for i, step in enumerate(ew.SEQUENCE_STEPS):
        if i == 0:
            # step 1 has no predecessor and never refuses on the sequence
            ew.require_sequence(step, enforce=True)
            ew.write_sequence_marker(step, produced={"n": 0})
            continue
        ew.require_sequence(step, enforce=True)      # predecessor present
        ew.write_sequence_marker(step, produced={"n": i})

    for i, step in enumerate(ew.SEQUENCE_STEPS[1:], 1):
        predecessor = ew.sequence_marker_path(ew.SEQUENCE_STEPS[i - 1])
        kept = predecessor.read_text()
        predecessor.unlink()
        with pytest.raises(ew.SequenceViolation) as exc:
            ew.require_sequence(step, enforce=True)
        assert ew.SEQUENCE_STEPS[i - 1] in str(exc.value)
        predecessor.write_text(kept)


def test_a_marker_written_under_another_freeze_commit_is_not_a_marker(
        tmp_path, monkeypatch):
    """§8.4: "A marker written under a different freeze commit is not a marker
    for this run."
    """
    monkeypatch.setattr(ew, "SEQUENCE_DIR", tmp_path / "sequence")
    monkeypatch.setattr(ew, "git_head", lambda rev="HEAD": "commit-one")
    ew.write_sequence_marker(ew.SEQUENCE_STEPS[0], produced={"n": 0})
    ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=True)

    monkeypatch.setattr(ew, "git_head", lambda rev="HEAD": "commit-two")
    with pytest.raises(ew.SequenceViolation) as exc:
        ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=True)
    assert "different freeze commit" in str(exc.value)


def test_the_markers_record_what_8_4_asks_them_to(tmp_path, monkeypatch):
    """"Each marker records the step name, the UTC completion time, the freeze
    commit under which it was written, the harness file digests at that moment,
    and a digest of what the step produced."
    """
    monkeypatch.setattr(ew, "SEQUENCE_DIR", tmp_path / "sequence")
    marker = ew.write_sequence_marker(ew.SEQUENCE_STEPS[2],
                                      produced={"shards": ["a", "b"]})
    assert marker["step"] == "step3_shards"
    assert marker["completed_at"] and marker["freeze_commit"] is not None
    assert set(marker["harness"]) == set(ew.HARNESS_FILES)
    assert len(marker["produced_digest"]) == 64
    assert marker["produced"] == {"shards": ["a", "b"]}


def test_the_launcher_is_a_valid_shell_script(tmp_path):
    """`sh -n` parses it without running it."""
    path = tmp_path / ew.LAUNCH_NAME
    path.write_text(ew.launch_script(ew.EVWIDEN_DIR))
    done = subprocess.run(["sh", "-n", str(path)], capture_output=True)
    assert done.returncode == 0, done.stderr.decode()


# ==========================================================================
# 15. the CLI
# ==========================================================================

def test_the_cli_writes_the_launcher_and_exits_clean(monkeypatch, tmp_path,
                                                    capsys):
    """...after the freeze, and into the preregistered run directory (§8.2)."""
    monkeypatch.setattr(ew, "_frozen_now", lambda: True)
    monkeypatch.setattr(ew, "EVWIDEN_DIR", tmp_path)
    assert ew.main(["--script", "--dir", str(tmp_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["launch"].startswith("nohup sh ")
    assert (tmp_path / ew.LAUNCH_NAME).exists()
    assert "heredoc" in printed["note"]


def test_the_cli_reports_a_typed_refusal_as_stop_and_exit_two(tmp_path, capsys):
    """The `RecalError` convention §5.1 adopts: `STOP: …` with the type, exit 2."""
    assert ew.main(["--merge", "--dir", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert out.startswith("STOP: ")
    assert "Error" in out.split(":")[1] or "Failed" in out or "Mismatch" in out


def test_the_cli_refuses_a_malformed_shard_spec(capsys):
    assert ew.main(["--run", "--shard", "one-of-four"]) == 2
    assert "must be i/N" in capsys.readouterr().out


# ==========================================================================
# 16. the pinned artifacts — read-only, no fits, skipped where they are absent
# ==========================================================================

@pytest.fixture(scope="module")
def real():
    """The pinned world, loaded once. READ-ONLY, and no fit runs here.

    §10 makes a real-archive fit before the §6 freeze commit an invalidation.
    Reading the archive to recompute `e` is not a fit: it is arithmetic on
    committed bytes, and it is how §8.3 step 2's membership digests are produced
    in the first place.
    """
    corpus = ew.load_corpus()
    played = ew.load_archive()
    ledger = ew.load_walk_ledger()
    return corpus, played, ledger


@pinned
def test_the_four_pinned_digests_are_the_documents():
    """§0.1's table, verified by the recipe the document prints."""
    assert ew.sha256_file(PINNED_CORPUS) == ew.CORPUS_SHA256
    assert ew.sha256_file(PINNED_ARCHIVE) == ew.ARCHIVE_SHA256
    assert ew.sha256_file(PINNED_LEDGER) == ew.WALK_LEDGER_SHA256
    assert ew.sha256_file(ew.CONFIG_PATH) == ew.CONFIG_SHA256


@pinned
def test_the_corpus_the_archive_and_the_ledger_have_the_pinned_shapes(real):
    corpus, played, ledger = real
    assert len(corpus) == 2280
    assert corpus["block"].nunique() == 212
    assert len(played) == 4560
    assert len(ledger) == 212
    ew.assert_ledger_covers(corpus, ledger)
    assert ew.check_corpus_scores(corpus)["max_abs_diff"] <= 1e-12


@pinned
def test_the_harness_reproduces_the_documents_evidence_census(real):
    """§0.4, recomputed through the harness's own code: 4,240 club-cutoff cells,
    `e` at 0.00 / 5.70 / 18.76 / 51.97 / 60.21, 25 cells under 3 and 13 under 1
    — every one of them already widened."""
    corpus, played, ledger = real
    table = ew.evidence_table(corpus, played)
    values = np.array([v for per_block in table.values()
                       for v in per_block.values()])
    assert values.size == ew.EXPECTED_CELLS
    assert round(float(values.min()), 2) == 0.00
    assert round(float(np.percentile(values, 1)), 2) == 5.70
    assert round(float(np.percentile(values, 5)), 2) == 18.76
    assert round(float(np.median(values)), 2) == 51.97
    assert round(float(values.max()), 2) == 60.21
    assert int((values < 3).sum()) == 25
    assert int((values < 1).sum()) == 13
    # "every one already widened" — no cell under 3 is a NEW cell
    assert ew.membership(corpus, played, ledger, e_star=3.0).new_cells == ()


@pinned
def test_the_harness_reproduces_the_documents_grid_table(real):
    """§1.4's table, recomputed: thin / already widened / treated / blocks."""
    corpus, played, ledger = real
    expected = {                      # e*: (thin, already, treated, blocks)
        1.0: (12, 12, 0, 12),
        3.0: (24, 24, 0, 24),
        5.0: (39, 32, 7, 34),
        8.0: (66, 33, 33, 50),
        10.0: (85, 33, 52, 62),
        12.0: (110, 33, 77, 78),
    }
    for star, (thin, already, treated, blocks) in expected.items():
        m = ew.membership(corpus, played, ledger, e_star=star)
        assert (len(m.thin), len(m.already_widened), len(m.treated),
                len(m.blocks)) == (thin, already, treated, blocks), star


@pinned
def test_the_harness_reproduces_the_frozen_membership(real):
    """§2.2 and §2.3, through `membership_digests`'s own count checks: 85 thin,
    52 treated, 51 cells of which 47 reach a fixture, 78 openings, 820 control
    fixtures, 46 incumbent-widened fixtures, and the per-season split."""
    corpus, played, ledger = real
    out = ew.membership_digests(corpus, played, ledger)
    assert out["counts"] == {
        "thin": 85, "treated": 52, "new_cells": 51, "new_cells_playing": 47,
        "fit_openings": 78, "control_fixtures": 820, "primary_blocks": 62,
        "cells": 4240, "incumbent_fixtures": 46}
    assert out["thin_by_season"] == {"2019/20": 26, "2020/21": 11,
                                     "2021/22": 12, "2022/23": 12,
                                     "2023/24": 12, "2024/25": 12}
    assert len(out["keys"]["thin"]) == 85
    assert len(out["keys"]["treated"]) == 52
    assert set(out["keys"]["treated"]) <= set(out["keys"]["thin"])
    assert all(len(v) == 64 for v in out["digests"].values())


@pinned
def test_the_51_cells_concentrate_on_the_nine_club_seasons_the_document_names(
        real):
    """§2.2: "They concentrate on nine club-seasons — three returning-thin
    (aston_villa 2019/20, norwich 2019/20, sheffield_united 2023/24) and six
    cold-start tails"."""
    corpus, played, ledger = real
    m = ew.membership(corpus, played, ledger)
    season_of = {str(b): str(part["season"].iloc[0])
                 for b, part in corpus.groupby("block")}
    got = {(season_of[block], club) for block, club in m.new_cells}
    assert got == {
        ("2019/20", "aston_villa"), ("2019/20", "norwich"),
        ("2019/20", "sheffield_united"), ("2020/21", "leeds"),
        ("2021/22", "brentford"), ("2022/23", "nottm_forest"),
        ("2023/24", "luton"), ("2023/24", "sheffield_united"),
        ("2024/25", "ipswich")}


@pinned
def test_the_fit_schedule_is_78_openings_over_820_fixtures(real):
    """§2.3 and §3.2, with `fit_points`' own count check switched on."""
    corpus, played, ledger = real
    points = ew.fit_points(corpus, played=played, ledger=ledger)
    assert len(points) == 78
    assert sum(len(p.match_ids) for p in points) == 820
    primary = set(ew.membership(corpus, played, ledger).blocks)
    assert primary <= {p.cutoff for p in points}
    # the shards still partition the real schedule
    for n in (1, 4):
        seen = [p.cutoff for i in range(n)
                for p in ew.shard_points(points, i, n)]
        assert sorted(seen) == sorted(p.cutoff for p in points)


@pinned
def test_the_table_leg_enumerates_the_16_cells_the_document_names():
    """§3.3, recomputed from the pinned archive by the §0.3 recipe and
    `count_volatility_arm` at each scheduled cutoff. No fit and no simulation:
    this is the enumeration the §8.3 commit freezes."""
    from epl import baseline, simretro

    matches = baseline.load_matches()
    cells = ew.table_cells(matches)
    whole = len(simretro.SEASONS) * len(simretro.COMPARISON_CUTOFFS)
    assert whole - len(cells) == len(ew.EXCLUDED_CELLS) == 3
    assert len(cells) == 32
    treated = {(c["season"], c["cutoff_label"]): c["treated_clubs"]
               for c in cells if c["treated_clubs"]}
    assert len(treated) == 15
    assert len(cells) - len(treated) == 17
    # §0.6: the ONE treated cell the census cost this design
    assert ("2019/20", "MW0") not in treated
    assert treated[("2019/20", "MW6")] == ["aston_villa", "norwich",
                                           "sheffield_united"]
    assert treated[("2023/24", "MW0")] == ["sheffield_united"]
    # the one Hull-analogue, §0.5's Sunderland cells
    for label in ("MW0", "MW3", "MW6"):
        assert treated[("2025/26", label)] == ["sunderland"]
    assert ("2025/26", "MW10") not in treated
    # cells[0] is now 2019/20 MW3, the first PRICEABLE cell in schedule order
    assert cells[0]["season"] == "2019/20" and cells[0]["cutoff_label"] == "MW3"
    assert round(cells[0]["evidence"]["aston_villa"], 2) == 7.47


def test_the_per_label_treated_census_is_a_binding_pin(tmp_path, monkeypatch):
    """§3.3, conformance row L14. "**This per-label census is a binding pin, not
    a table in prose.** `EXPECTED_TREATED_BY_LABEL = {MW0: 3, MW3: 2, MW6: 7,
    MW10: 4, MW19: 0}` must be verified by `table_cells(check=True)`, which
    today verifies only the 35/16 totals."

    The reason is not tidiness: "**'MW6 is the only label at which every cell is
    treated' is the entire stated ground for naming MW6 the deciding
    horizon**". If that stops being true, the ground for the deciding horizon
    has moved and the harness must refuse rather than carry on. The audit found
    the pin "referenced nowhere in the module or the tests" — a dead constant.
    """
    assert ew.EXPECTED_TREATED_BY_LABEL == {"MW0": 2, "MW3": 2, "MW6": 7,
                                            "MW10": 4, "MW19": 0}
    # MW6 is the only label at which EVERY cell is treated, which is the ground
    # — and after §0.6 that is a statement about TWO censuses, because the
    # labels no longer hold seven cells each
    assert ew.EXPECTED_TREATED_BY_LABEL[ew.MW6_LABEL] == \
        ew.EXPECTED_CELLS_BY_LABEL[ew.MW6_LABEL]
    assert [lab for lab in ew.EXPECTED_CELLS_BY_LABEL
            if ew.EXPECTED_TREATED_BY_LABEL[lab]
            == ew.EXPECTED_CELLS_BY_LABEL[lab]] == [ew.MW6_LABEL]

    cells = _cells()
    assert ew.assert_table_census(cells)["PASS"] is True

    # a perturbation that keeps the 35/16 TOTALS and moves one cell between
    # labels — invisible to v1's check, and the whole point of the pin
    moved = [dict(c) for c in cells]
    give = next(c for c in moved
                if c["cutoff_label"] == "MW0" and c["treated_clubs"])
    take = next(c for c in moved
                if c["cutoff_label"] == "MW3" and not c["treated_clubs"])
    take["treated_clubs"] = list(give["treated_clubs"])
    give["treated_clubs"] = []
    assert sum(1 for c in moved if c["treated_clubs"]) == 15   # totals intact
    with pytest.raises(ew.MembershipMismatch) as exc:
        ew.assert_table_census(moved)
    assert "per-label" in str(exc.value)
    assert "MW6 is the only label" in str(exc.value)


@pinned
def test_the_hull_analogue_carries_the_evidence_the_document_records():
    """§0.5: Sunderland at the 2025/26 opener — `e` = 0.172, the Hull
    configuration one season early, and not provisional."""
    from epl import baseline

    matches = baseline.load_matches()
    played = matches.loc[matches["played"]].copy()
    played["date"] = pd.to_datetime(played["date"]).dt.normalize()
    e = ew.effective_evidence("2025-08-15", played, ["sunderland"])
    assert round(e["sunderland"], 3) == 0.172


@pytest.mark.skipif(not PREREG.exists(), reason="the preregistration is absent")
def test_the_module_does_not_drift_from_the_document_it_implements():
    """The constants a reader would check by grep, checked by a test instead."""
    text = PREREG.read_text()
    assert "`e* = 10.0` frozen" in text
    assert "**ADOPT the evidence-mass re-key" in text
    assert "`dc_evwiden`" in text
    assert ew.CORPUS_SHA256 in text
    assert ew.ARCHIVE_SHA256 in text
    assert ew.WALK_LEDGER_SHA256 in text
    assert ew.CONFIG_SHA256 in text
    assert "epl-evwiden-3" in text and ew.SCHEMA_ID == "epl-evwiden-3"
    for name in ew.HARNESS_FILES:
        assert name in text
    # the numbers §4 gates on, as the document writes them
    assert "-0.0010" in text.replace("−", "-")
    assert "+0.0002" in text


def test_the_harness_cites_no_clause_the_law_does_not_contain():
    """§8.1 and the v2 preamble: "**There are no repair sections and no
    supersession index, because there is nothing to supersede.** Every clause
    below is the operative clause."

    v1's law was its original text AS AMENDED by two repair rounds, so the
    harness cited those rounds' identifiers at the code each one governed —
    thirty-odd of them, none of which exists in v2. A reader who greps the
    harness for the clause that justifies a line must land in the law rather
    than in a document that decides nothing, so every citation is now a § of v2
    and this test is what keeps it that way.

    The one legitimate exception is a line that is discussing v1's death: §8.1
    names v1's own rule when it explains what killed it, and a quotation of that
    sentence names it too. Such a line says "v1" on its face.
    """
    import re

    retired = re.compile(r"\bR2?-(?:B|I|M|X|H|Z)\d*\b|\bR2-0\b")
    scanned = [Path("epl/evwiden.py"), Path("epl/tests/test_evwiden.py")]
    # ...and THE DOCUMENT ITSELF. The cross-model review's hygiene finding was
    # that the retired-ID test "scans code/tests, not v2 itself", while v1's
    # own retired identifier remained operative shorthand in four places of the
    # law — so the thing the citations are supposed to point AT carried them.
    if PREREG.exists():
        scanned.append(PREREG)
    for path in scanned:
        offenders = [line.strip() for line in path.read_text().splitlines()
                     if retired.search(line) and "v1" not in line]
        assert not offenders, f"{path}: {offenders[:3]}"

    # ...and the round-numbering vocabulary goes with them: v2 has no rounds,
    # so a line that uses it is either talking about v1 or is out of date
    harness = Path("epl/evwiden.py").read_text()
    for phrase in ("repair round", "both rounds", "round one", "round two",
                   "the re-review"):
        stale = [line.strip() for line in harness.splitlines()
                 if phrase in line.lower() and "v1" not in line]
        assert not stale, (phrase, stale[:3])

    # No § of v2 supersedes another § of v2 — "every clause below is the
    # operative clause". (Describing v1's SUPERSEDED design is fine, and is how
    # this module records what each guard is for.)
    self_supersession = re.findall(r"§[\d.]+(?:\([a-c]\))?\s+supersedes", harness)
    assert not self_supersession, self_supersession


@pytest.mark.skipif(not PREREG.exists(), reason="the preregistration is absent")
def test_the_harness_is_bound_to_v3_and_v2_and_v1_are_only_lineage():
    """§8.1: v1 is invalidated by its own R-B6; v2 cannot be run as written.

    The freeze guard, the first-fit record and the evidence object all name a
    preregistration by path. If any of them still names v1, the harness is
    binding itself to an invalidated document — and the two ADVI fits that
    ended v1 would carry into v2's regime.
    """
    assert ew.PREREG_PATH.name == "epl_widening_prereg_v3.md"
    assert ew.SCHEMA_ID == "epl-evwiden-3"
    text = PREREG.read_text()
    assert "invalidated the\nsame day under v1's own R-B6" in text  # v1's rule
    # ...and v2 is closed for a different reason, stated as one
    assert "**cannot be run as written**" in text
    # the sole law says so about itself
    assert "There are no repair sections and no supersession index" in text


def test_the_read_only_store_accessor_never_builds_and_takes_no_build_flag():
    """§8.2's mechanism, not its promise.

    "It opens the existing store parquet and returns it. If the store parquet is
    absent it raises `StoreNotBuilt` and stops. It never builds, never writes,
    never unlinks, and takes no 'build if missing' argument."
    """
    import inspect

    params = inspect.signature(ew.read_only_store).parameters
    # a "build if missing" argument is exactly the escape hatch §8.2 forbids
    assert not any(k for k in params
                   if "build" in k or "rebuild" in k or "create" in k), params
    # the CALLS it makes, read off the syntax tree — the prose in its docstring
    # and in its refusal message names `build_store` and "never unlinks", which
    # is the citation of the defect, not the defect
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(ew.read_only_store)))
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            called.add(f.attr if isinstance(f, ast.Attribute)
                       else getattr(f, "id", ""))
    assert "BitemporalStore" in called, "the accessor OPENS a store"
    for forbidden in ("build_store", "unlink", "write", "mkdir", "to_parquet"):
        assert forbidden not in called, forbidden


def test_the_read_only_accessor_refuses_an_absent_store_and_creates_nothing(
        tmp_path):
    """`StoreNotBuilt`, and the directory stays as it was found."""
    root = tmp_path / "store"
    with pytest.raises(ew.StoreNotBuilt):
        ew.read_only_store(root=root)
    assert not root.exists()

    root.mkdir()
    with pytest.raises(ew.StoreNotBuilt):
        ew.read_only_store(root=root)
    assert list(root.iterdir()) == []


def test_the_pre_freeze_commands_cannot_reach_build_store(monkeypatch, tmp_path):
    """§8.2's committed test, behavioural: "it executes all three commands
    against a store root whose parquet has been removed, requires
    `StoreNotBuilt` from each, and requires that nothing was created".

    v1's `--membership`, `--plan` and `--freeze-block` all reached `table_cells`,
    which called `epl.fit.build_store(played)` at the DEFAULT root, and
    `build_store` can unlink and rewrite the shared `results.parquet`. A
    pre-freeze command that can delete and rebuild the project's point-in-time
    store is not read-only in any sense the word carries.
    """
    import epl.fit as epl_fit

    root = tmp_path / "store"
    root.mkdir()
    calls = []

    def forbidden(*a, **k):                       # pragma: no cover — must not run
        calls.append((a, k))
        raise AssertionError("build_store was reached from a pre-freeze path")

    monkeypatch.setattr(epl_fit, "build_store", forbidden)
    monkeypatch.setattr(ew.paths, "STORE_DIR", root)

    corpus, played, ledger = _world()
    matches = played.assign(played=True)
    for call in (lambda: ew.table_cells(matches, played, check=False),
                 lambda: ew.default_table_cells(played)):
        with pytest.raises(ew.StoreNotBuilt):
            call()
    assert calls == []
    assert list(root.iterdir()) == []


def test_the_shared_store_is_byte_untouched_by_every_pre_freeze_command(
        tmp_path, monkeypatch):
    """§8.2's second committed test: the shared store's bytes AND mtime are
    unchanged by all three pre-freeze commands.

    The store here is a stand-in with the real one's shape — the point is that
    the accessor opens it and hands it back, and that no code path on the way to
    a pre-freeze answer rewrites the file it read.
    """
    root = tmp_path / "store"
    root.mkdir()
    table = root / "results.parquet"
    table.write_bytes(b"not really a parquet, and it must stay these bytes")
    before = (table.read_bytes(), table.stat().st_mtime_ns)
    monkeypatch.setattr(ew.paths, "STORE_DIR", root)

    # the accessor opens the store root; it neither validates nor rewrites the
    # bytes, which is what makes "read-only" a property of the code
    store = ew.read_only_store(root=root)
    assert store is not None
    assert (table.read_bytes(), table.stat().st_mtime_ns) == before


def test_the_canary_never_rebuilds_the_shared_point_in_time_store(monkeypatch):
    """§8.3 closes the write set, and `epl.fit.build_store` UNLINKS and rewrites
    `data/epl/fit/store/results.parquet` whenever the row set differs.

    The canary builds a store from a deliberately corrupted frame. Under the
    default root that would overwrite production state this experiment is not
    allowed to write — silently, and only on the machine that has the store.
    Every build therefore goes to a temporary root, and this test is the guard
    that it stays that way.
    """
    import epl.fit as epl_fit
    import wcmodel.model.volatility_diagnostic as vd

    roots = []

    def fake_build_store(matches=None, root=None, rebuild=False):
        roots.append(root)
        return object()

    monkeypatch.setattr(epl_fit, "build_store", fake_build_store)
    monkeypatch.setattr(vd, "count_volatility_arm",
                        lambda store, cutoff, clubs, config=None: pd.DataFrame(
                            {"team": list(clubs),
                             "volatility_flag": [False] * len(clubs),
                             "few_games_flag": [False] * len(clubs)}))

    corpus, played, ledger = _world()
    record = ew._run_all_canaries(corpus, played, ledger, results_canary=False)
    assert record["PASS"] is True
    assert record["results_canary_run"] is False
    assert roots and all(r is not None for r in roots)
    default = str(ew.paths.STORE_DIR.resolve())
    assert all(not str(Path(r).resolve()).startswith(default) for r in roots)


# ==========================================================================
# 17. the refusal inventory, and `--verify`
# ==========================================================================

def test_every_refusal_type_7_1_names_exists_and_derives_from_the_base():
    """§7.1's table, by name. A typed name is a promise the preregistration
    made; this is the test that it was kept.

    v2 adds three that v1 never had, and each one names a defect v1's own
    reviews found: ``StoreNotBuilt`` (§8.2's read-only accessor, which never
    builds), ``SequenceViolation`` (§8.4's completion markers) and
    ``FreezeStateUnverified`` (§8.6's guard, which establishes the state rather
    than accepting a caller's boolean).
    """
    named = ("CorpusMissing", "CorpusDigestMismatch", "CorpusShapeMismatch",
             "ArchiveDigestMismatch", "LedgerDigestMismatch", "ConfigNotFrozen",
             "MembershipMismatch", "PredicateMismatch", "EvidenceLeak",
             "CutoffLeak", "CanaryFailed", "EvidenceCanaryFailed",
             "ControlMismatch", "UntreatedMoved", "TableIdentityBreak",
             "FitFailed", "UnpriceableFixture", "ScoreMismatch",
             "SchemaMismatch", "RowConflict", "ShardFailed", "MergeIncomplete",
             "TableMCImprecise", "StoreNotBuilt", "SequenceViolation",
             "FreezeStateUnverified")
    assert len(named) == 26
    for name in named:
        cls = getattr(ew, name)
        assert issubclass(cls, ew.EvWidenError), name
        assert issubclass(cls, RuntimeError), name


def test_the_harness_invents_no_refusal_the_document_never_wrote():
    """`epl.freshsweep`'s ruling, applied here: a condition §10 pre-states as an
    invalidation but §7.1 never named refuses as the BASE class rather than
    under a name invented after the fact."""
    import inspect

    subclasses = {name for name, obj in vars(ew).items()
                  if inspect.isclass(obj) and issubclass(obj, ew.EvWidenError)
                  and obj is not ew.EvWidenError}
    named = {"CorpusMissing", "CorpusDigestMismatch", "CorpusShapeMismatch",
             "ArchiveDigestMismatch", "LedgerDigestMismatch", "ConfigNotFrozen",
             "MembershipMismatch", "PredicateMismatch", "EvidenceLeak",
             "CutoffLeak", "CanaryFailed", "EvidenceCanaryFailed",
             "ControlMismatch", "UntreatedMoved", "TableIdentityBreak",
             "FitFailed", "UnpriceableFixture", "ScoreMismatch",
             "SchemaMismatch", "RowConflict", "ShardFailed", "MergeIncomplete",
             "TableMCImprecise", "StoreNotBuilt", "SequenceViolation",
             "FreezeStateUnverified",
             # v3 §7.1: the census record is a PIN (§0.1), and this document's
             # table leg is scoped by it — "a record that is not the record
             # scopes nothing"
             "FeasibilityRecordMismatch"}
    assert subclasses == named
    # §7.1 counts it both ways so neither reading is wrong: 27 named refusals,
    # 28 classes counting the base they all derive from.
    assert len(subclasses) == 27 and len(subclasses | {"EvWidenError"}) == 28
    # the pre-freeze-fit invalidation is one of the unnamed ones, and refuses
    # as the base class
    with pytest.raises(ew.EvWidenError) as exc:
        ew.require_harness_freeze()
    assert type(exc.value) is ew.EvWidenError


def test_verify_re_derives_the_headline_from_the_committed_evidence(tmp_path):
    """The check a reader of the repository can run: three routes to the number
    rather than one number copied twice."""
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, rows, None, directory=out, manifest=False)

    checked = ew.verify(tmp_path, shards=1, evidence=out / "widening.json",
                        )
    assert checked["PASS"] is True
    sources = {c["source"] for c in checked["checks"] if c.get("checked")}
    assert sources == {"per_fixture_csv", "shard_ledgers"}
    assert all(c["delta_mean"] <= 1e-12 for c in checked["checks"]
               if c.get("checked"))


def test_verify_refuses_a_verdict_that_does_not_match_its_own_evidence(tmp_path):
    """A verdict nobody can recompute is exactly what `reports/evidence/`
    exists to prevent."""
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, rows, None, directory=out, manifest=False)

    published = json.loads((out / "widening.json").read_text())
    published["estimand"]["mean"] = float(published["estimand"]["mean"]) + 1e-6
    (out / "widening.json").write_text(json.dumps(published))
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.verify(tmp_path, shards=1, evidence=out / "widening.json")
    assert "does not re-derive" in str(exc.value)


def test_verify_refuses_when_there_is_no_published_verdict(tmp_path):
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.verify(tmp_path, shards=1, evidence=tmp_path / "absent.json")
    assert "never finished" in str(exc.value)


def test_no_live_2026_27_quantity_can_enter_this_experiment():
    """§10: "The 27.9→15.9 counterfactual, or any live-2026/27 quantity, enters
    any gate" is an invalidation, and §1.2 rules the counterfactual "a
    motivating observation OUTSIDE the evidence base… the harness does not
    recompute it".

    The scoring window stops at 2024/25 and the table leg's seasons come from
    `simretro.SEASONS`, which stops at 2025/26. Neither reaches the live season,
    and no number from it appears anywhere in the harness.
    """
    from epl import simretro

    assert max(ew.CORPUS_SEASONS) == "2024/25"
    assert "2026/27" not in simretro.SEASONS
    assert max(simretro.SEASONS) == "2025/26"
    assert ew.HULL_ANALOGUE == ("2025/26", "sunderland")

    source = (ew.paths.REPO_ROOT / "epl" / "evwiden.py").read_text()
    for forbidden in ("2026/27", "27.885", "0.27885", "15.9%", "58.71"):
        assert forbidden not in source, forbidden


def test_no_results_canary_cannot_follow_the_run_past_the_freeze(tmp_path):
    """§7.3 makes `walkforward.point_in_time_canary` a precondition on the REAL
    archive after the freeze. `--no-results-canary` exists for the synthetic
    audit's clock, and a flag that saved time before the freeze must not be able
    to silently remove a precondition after it."""
    path = tmp_path / ew.CANARY_NAME
    ew.write_canaries({"PASS": True, "evidence": {"PASS": True},
                       "results_canary_run": False}, path)

    # before the freeze, an audit record is enough to keep the ORDER
    assert ew.require_run_preconditions(tmp_path, require_results=False)

    # after it, the same record is refused by name
    with pytest.raises(ew.CanaryFailed) as exc:
        ew.require_run_preconditions(tmp_path, require_results=True)
    assert "--no-results-canary" in str(exc.value)

    ew.write_canaries({"PASS": True, "evidence": {"PASS": True},
                       "results": {"PASS": True}, "results_canary_run": True},
                      path)
    assert ew.require_run_preconditions(tmp_path, require_results=True)


# ==========================================================================
# 18. no selection on outcomes — ultra-review lesson 2, and §2.1's ruling
# ==========================================================================

def test_the_population_is_selected_from_the_past_and_never_from_the_outcome(
        tmp_path):
    """§1.4's rule: thin is `min-side e < e*` AT THE BLOCK CUTOFF, a sum over
    matches strictly before it. Nothing about which fixtures enter the estimand
    can depend on how they turned out.

    Tested on the real selection path: permute every outcome, rewrite every
    forecast, and demand the thin and treated sets come back identical — the
    ultra-review's "any selection step must be prequential/past-only",
    satisfied here by there being no selection step at all.
    """
    corpus, played, ledger = _world()
    before = ew.membership(corpus, played, ledger, e_star=ew.E_STAR)

    scrambled = corpus.copy()
    scrambled["y"] = (scrambled["y"] + 1) % 3
    scrambled[["dc_home", "dc_draw", "dc_away"]] = \
        scrambled[["dc_away", "dc_home", "dc_draw"]].to_numpy()
    scrambled["dc_rps"] = score_mod.rps(
        scrambled[list(ew._PROB_COLUMNS)].to_numpy(float),
        scrambled["y"].to_numpy())
    after = ew.membership(scrambled, played, ledger, e_star=ew.E_STAR)

    assert after.thin == before.thin
    assert after.treated == before.treated
    assert after.new_cells == before.new_cells
    assert after.blocks == before.blocks
    # and the fits the run would pay for are the same fits
    assert ew.fit_openings(scrambled, played, ledger) == \
        ew.fit_openings(corpus, played, ledger)


def test_the_population_does_not_move_when_the_archive_gains_a_later_match():
    """The same property from the other side: evidence is a sum over matches
    STRICTLY BEFORE the block cutoff, so a result that lands after it cannot
    retroactively make a fixture thick."""
    corpus, played, ledger = _world()
    before = ew.membership(corpus, played, ledger)
    later = pd.concat([played, pd.DataFrame([{
        "match_id": "future1", "date": pd.Timestamp(CUT_C) + pd.Timedelta(days=5),
        "home_key": "stale", "away_key": "rich", "fthg": 3, "ftag": 0,
        "played": True, "season": "hist"}])], ignore_index=True)
    assert ew.membership(corpus, later, ledger).thin == before.thin


def test_the_grid_is_reported_and_the_verdict_cannot_read_it():
    """§2.1: "No parameter is selected anywhere in this experiment… every grid
    point's estimand analogue is published as a secondary with ZERO DECISION
    WEIGHT", and §2.1 pre-states the cost: a neighbour that looks better is
    selection-on-outcome, may not be adopted, and carries exploratory standing
    only.

    `adoption` takes the estimand's own point estimate and its two intervals.
    It has no parameter through which a grid point could reach it.
    """
    import inspect

    signature = inspect.signature(ew.adoption)
    assert list(signature.parameters) == ["delta", "ci95_block", "ci95_season",
                                          "table"]
    # a spectacular grid point cannot change a missing verdict
    miss = ew.adoption(-0.0001, [-0.001, 0.002], [-0.001, 0.002],
                       _PASSING_TABLE)
    assert miss["verdict"] == "DC_NATIVE STANDS"
    assert "grid" not in json.dumps(miss)


def test_every_secondary_says_in_its_own_output_that_it_decides_nothing(
        tmp_path):
    """§3: "Everything in §3.1 and §3.4 is published with the result and DECIDES
    NOTHING." A claim in a document is a claim; a field in the output travels
    with the number to wherever it gets quoted."""
    rows = _merged(tmp_path)
    result = ew.estimand(rows, corpus_rows=len(rows))
    assert result["secondaries_decide"] == "nothing"
    assert result["secondaries"]["full_population"]["decides"] == "nothing"
    assert result["decides"].startswith("nothing")


# ==========================================================================
# §6 — the power simulation, committed
# ==========================================================================

def test_the_conformance_report_computes_its_own_power_run():
    """§6.3: "`power_reproduces()` must compare the committed run against this
    table through the **real** comparison — not a stubbed power object."

    This module's own helper used to build that object and hand it to
    `implementation_report`/`freeze_block`, which is how the in-tree audit's
    seed (u) got in: a fabricated six-row dict carrying `PUBLISHED_POWER`'s own
    numbers plus a 101-long dummy curve rendered the §8.3 block in 11.5 s with
    all eighteen rows green. There is nowhere to hand one now — the parameter is
    gone from all three — and the comparison's default is
    `committed_power_run()`, which takes no arguments at all.
    """
    import inspect

    assert ew._no_parameter(ew.implementation_report, "power")
    assert ew._no_parameter(ew.assert_implements_document, "power")
    assert ew._no_parameter(ew.freeze_block, "power", "pre_freeze_runs")
    assert not inspect.signature(ew.committed_power_run).parameters
    # ...and it is the committed simulation, EXECUTED — see the test below,
    # which is the one that binds the obligation
    assert "power_simulation()" in inspect.getsource(ew.committed_power_run)


def test_no_process_state_may_stand_in_for_the_power_simulation(monkeypatch):
    """The adjudication of 2026-08-29, F9 (V3-B3). "The module-level
    `_POWER_RUN` cache is an unbound authority over `committed_power_run()`.
    Pre-populating it skips the committed power simulation and supplies L16's
    result. The conformance artifact records only the wrapper's passed outcome,
    not whether the simulation executed."

    F9: "remove the `_POWER_RUN` module cache entirely; the power simulation
    re-runs when asked (~20s); no process state may substitute for it." L16's
    whole obligation is that the numbers came out of the committed
    `power_simulation()`, and a memo is a place to put numbers that did not.
    """
    import inspect

    calls: list[int] = []

    def counted(*a, **kw):
        calls.append(1)
        return {"rows": [], "counted": True}

    monkeypatch.setattr(ew, "power_simulation", counted)
    assert ew.committed_power_run() == {"rows": [], "counted": True}
    assert ew.committed_power_run() == {"rows": [], "counted": True}
    # the simulation RAN both times: nothing between the caller and the
    # committed code holds an answer from before
    assert calls == [1, 1]
    # ...and there is no module-level container to plant one in
    assert not hasattr(ew, "_POWER_RUN")
    # the BODY reads one global and it is the committed simulation — a name
    # check on the compiled code rather than on the prose around it
    assert ew.committed_power_run.__code__.co_names == ("power_simulation",)
    assert "return power_simulation()" in inspect.getsource(
        ew.committed_power_run)


def test_the_power_simulation_is_committed_code_at_the_ruled_path():
    """§6: "§6's six power numbers were produced by uncommitted scratch
    code… A preregistration that publishes six deciding-adjacent numbers from
    code no one can execute is doing the thing it exists to stop."

    Module `epl/evwiden.py`, function `power_simulation()`, CLI
    `python -m epl.evwiden --power`, tests here, and it WRITES NOTHING."""
    import inspect

    assert callable(ew.power_simulation)
    assert ew.power_simulation.__module__ == "epl.evwiden"
    source = inspect.getsource(ew.power_simulation)
    for forbidden in ("write_text", "to_parquet", "open(", "savez"):
        assert forbidden not in source, forbidden
    cli = inspect.getsource(ew.main)
    assert "--power" in cli and "power_simulation(" in cli
    # the constants §6 freezes
    assert ew.POWER_REPLICATES == 2000 and ew.POWER_SEED == 20260827
    assert ew.POWER_GRID_POINTS == 101 and ew.POWER_GRID_STEP == 2e-4
    assert [s[1] for s in ew.POWER_SCENARIOS] == [0.005262, 0.014449, 0.036]
    assert ew.POWER_RHOS == (0.0, 0.5)
    assert ew.POWER_BAR == pytest.approx(-0.0016346153846153847, abs=1e-18)
    assert 2 * ew.POWER_BAR == pytest.approx(-0.0032692307692307695, abs=1e-18)
    assert len(ew.PUBLISHED_POWER) == 6


def test_the_mde_rules_are_interpolation_then_tie_then_exhaustion():
    """§6 freezes all three, in that order."""
    grid = np.array([-2e-4 * i for i in range(5)])
    # a grid point at exactly 0.80 IS the MDE, with no interpolation
    mde, note = ew._mde_from_curve(grid, np.array([0.0, 0.5, 0.80, 0.9, 1.0]))
    assert mde == grid[2] and "tie rule" in note
    # otherwise the FIRST adjacent pair bracketing 0.80, linearly interpolated
    mde, note = ew._mde_from_curve(grid, np.array([0.0, 0.5, 0.7, 0.9, 1.0]))
    assert mde == pytest.approx(grid[2] + 0.5 * (grid[3] - grid[2]))
    assert "linear interpolation" in note
    # and if 0.80 is never reached the table says so rather than extrapolating
    mde, note = ew._mde_from_curve(grid, np.array([0.0, 0.1, 0.2, 0.3, 0.4]))
    assert mde is None and "exhaustion rule" in note


@pinned
def test_the_bootstrap_shortcut_equals_the_protected_function(real):
    """§6: "A vectorised inner loop is permitted ONLY if a committed test
    asserts that its `(lo, hi, n_blocks)` equals the protected function's on the
    frozen structure, at three named noise draws, to 1e-15 — and reports
    `n_blocks` of 62 and 6. Absent that test, the shortcut is removed, not
    trusted." """
    corpus, played, ledger = real
    structure = ew.power_structure(corpus, played, ledger)
    for named_seed in (20260827, 20260814, 20260611):
        draw = np.random.default_rng(named_seed).standard_normal(
            structure["n_thin"]) * 0.005262
        week = ew.bootstrap_shortcut_matches(draw, structure["blocks"],
                                             n_boot=2000)
        season = ew.bootstrap_shortcut_matches(draw, structure["seasons"],
                                               n_boot=2000)
        assert week["PASS"] and season["PASS"], named_seed
        assert week["max_abs_diff"] <= 1e-15
        assert season["max_abs_diff"] <= 1e-15
        assert week["n_blocks"] == [62, 62]
        assert season["n_blocks"] == [6, 6]


@pinned
def test_the_power_structure_is_r_i2s_frozen_one(real):
    """§6's structure, and the counts are checked rather than typed in: the
    ASSIGNMENT of the 85 fixtures to their 62 week blocks is the corpus's own,
    which is what the week-block bootstrap actually resamples."""
    corpus, played, ledger = real
    s = ew.power_structure(corpus, played, ledger)
    assert s["n_thin"] == 85 == ew.POWER_N_THIN
    assert s["n_treated"] == 52 == ew.POWER_N_TREATED
    assert s["n_week_blocks"] == 62 == ew.POWER_N_WEEK_BLOCKS
    assert s["n_seasons"] == 6 == ew.POWER_N_SEASONS
    assert s["thin_by_season"] == (26, 11, 12, 12, 12, 12)
    assert s["treated_by_season"] == (21, 4, 7, 6, 7, 7)
    assert int(np.asarray(s["treated"]).sum()) == 52


@pinned
def test_the_power_simulation_runs_and_carries_its_own_construction(real):
    """A short run: the object it emits is the one `widening.json` carries, and
    every frozen choice is named in it."""
    corpus, played, ledger = real
    structure = ew.power_structure(corpus, played, ledger)
    out = ew.power_simulation(structure)
    assert len(out["rows"]) == 6
    assert out["bootstrap"]["seed"] == ew.BOOTSTRAP_SEED
    assert out["simulation_seed"] == ew.POWER_SEED
    assert "unattainable by construction" in out["structural_fact"]
    assert "SUBSTANTIALLY UNINFORMATIVE" in out["warning"]
    assert out["decides"].startswith("nothing")
    for row in out["rows"]:
        assert 0.0 <= row["power_at_bar"] <= 1.0
        assert len(row["curve"]) == ew.POWER_GRID_POINTS
        # the curve is monotone in delta up to Monte-Carlo error — common
        # random numbers across grid points are what make it so
        assert all(b >= a for a, b in zip(row["curve"], row["curve"][1:]))


@pinned
def test_the_freeze_block_refuses_while_a_power_number_is_unreproduced(
        monkeypatch, tmp_path, unrun_feasibility):
    """§8.3: "**`--freeze-block` refuses to render** while the conformance
    report has a red row, while §7.4's ancestry test is absent, or while §6.3's
    table is unreproduced."

    v2 removes v1's escape hatch: §6.3 says flatly that "these are the numbers
    the committed `power_simulation()` produces at the frozen constants above,
    and they are the document's numbers", so an unreproduced row is a defect in
    one of the two rather than an occasion for a dated note.

    The break is made in §6.3's PUBLISHED table rather than in a supplied
    ``power`` object, because there is no longer anywhere to supply one:
    `freeze_block`, `assert_implements_document` and `implementation_report`
    took a `power=` parameter, and the in-tree audit rendered this block in
    11.5 s from a fabricated six-row object with all eighteen rows green — L16
    among them. The comparison now runs the committed simulation itself, so the
    only way to make the row red is to make one of the two legs wrong.
    """
    published = [dict(r) for r in ew.PUBLISHED_POWER]
    published[0] = dict(published[0], power_at_bar=0.999)
    monkeypatch.setattr(ew, "PUBLISHED_POWER", tuple(published))
    # §8.5's artifact stands, derived from the rows as they actually ran, so
    # the refusal this test is about is the one it reaches
    monkeypatch.setattr(ew, "CONFORMANCE_ARTIFACT",
                        tmp_path / "evwiden_conformance.json")
    ew.write_conformance_artifact(
        {rid: ("passed" if ew.conformance_row(rid)["ok"] else "failed")
         for rid in ew.CONFORMANCE_ROWS})
    with pytest.raises(ew.EvWidenError) as exc:
        ew.freeze_block()
    assert "does not yet implement the document" in str(exc.value)
    assert "the document's numbers" in str(exc.value)
    assert "L16" in str(exc.value)

    report = ew.implementation_report()
    assert [r["id"] for r in report if not r["ok"]] == ["L16"]


@pinned
def test_the_conformance_report_is_eighteen_behavioural_rows():
    """§8.5: "**Every row of v2's report executes a scenario that fails under
    its own defect class. A row that cannot go red is not a row.**"

    v1's fourteen rows "checked field names, constants, callables, a subclass
    count and a substring — they could all be green while the obligations they
    were named for failed, and they were". The audit's table of what each row
    actually checked is the indictment: "three field names exist", "a
    test-function name occurs in working-tree text", "subclass count". And §8.4
    had no row at all, so the frozen sequence was ungraded.
    """
    report = ew.implementation_report()
    ids = [r["id"] for r in report]
    assert ids == [f"L{i}" for i in range(1, 19)], ids
    for row in report:
        # every row names the OBLIGATION and the SCENARIO it executes
        assert row["obligation"] and row["scenario"], row["id"]
        assert row["section"], row["id"]
    # §8.4's successor, §8.4's frozen sequence, has a row of its own — v1's
    # report had none
    assert any("§8.4" in r["section"] for r in report)
    assert all(r["ok"] for r in report), [r for r in report if not r["ok"]]


def test_the_report_is_not_believed_on_its_own_word():
    """§8.5's closing clause: "The test that reads the report may **not** simply
    assert that every self-reported row is green: it must independently execute
    at least the seeded scenarios of L5, L6, L7, L9, L11, L12 and L13, so that a
    report which lies about itself is caught by something other than itself."

    Those seven scenarios are executed by committed tests of their own, and this
    test is the index that binds each row to the test that re-runs it. A row
    whose independent test is deleted fails here.
    """
    independent = {
        "L5": ("test_parity_is_established_before_one_treated_simulation_runs",
               "test_no_require_parity_parameter_and_no_limit_on_the_oracle_exist"),
        "L6": ("test_the_pre_freeze_commands_cannot_reach_build_store",
               "test_the_read_only_accessor_refuses_an_absent_store_and_creates_nothing"),
        "L7": ("test_no_public_fit_surface_accepts_a_freeze_state_boolean",
               "test_no_scratch_directory_lets_the_pinned_archive_be_fitted_unfrozen"),
        "L9": ("test_a_step_without_its_predecessors_marker_refuses",
               "test_the_launcher_emits_exactly_the_five_steps_in_order"),
        "L11": ("test_the_sampler_digests_signature_is_pinned_to_run_and_tallies",
                "test_two_books_differing_only_in_provisional_hash_the_same_sampler_output"),
        "L12": ("test_the_real_engine_fit_refuses_a_difference_no_tolerance_would_see",
                "test_the_real_engine_fit_refuses_an_untreated_fixture_that_moved",
                "test_the_real_engine_fit_refuses_a_pass_two_pass_three_disagreement"),
        "L13": ("test_the_structural_zero_guard_is_two_sided_at_the_merge",),
    }
    here = globals()
    for row, names in independent.items():
        for name in names:
            assert callable(here.get(name)), f"{row}: {name} is missing"

    # ...and the index is not the check. §8.5 asks this test to EXECUTE the
    # seven scenarios, so a report that lies about itself is caught by
    # something other than itself. These are the seven, re-run here against the
    # production code rather than read off the report's own `ok` fields.
    import inspect

    # L5 — parity before treatment, and no bypass parameter
    cells = _cells()
    with pytest.raises(ew.TableIdentityBreak):
        ew.assert_parity_complete(cells, _parity_for(cells[:-1]))
    assert ew._no_parameter(ew.run_table, "require_parity", "limit")
    with pytest.raises(ew.TableIdentityBreak):
        ew.run_cell_arms("k", simulate=lambda *a: None, record=lambda *a: {},
                         books={}, parity_row=None, provisional_control=())

    # L6 — the pre-freeze commands are mechanically read-only
    with pytest.raises(ew.StoreNotBuilt):
        ew.read_only_store(root=Path("/nonexistent-store-root"))
    assert "build_store" not in ew._calls_made(ew.table_cells)

    # L7 — no freeze-state boolean, and merge's seams are refused
    for fn in (ew.Engine.__init__, ew.TableRunner.__init__,
               ew.ParityRunner.__init__, ew.run_fits, ew.run_table,
               ew.assert_may_fit, ew.simulate_arm, ew.run_canary,
               ew.freeze_block):
        assert ew._no_parameter(fn, "harness_frozen", "frozen", "freeze",
                                "check_implementation"), fn
    with pytest.raises(ew.EvWidenError):
        ew.merge(shards=ew.SHARDS, harness_frozen=True, require_canaries=False)

    # L9 — the launcher's preconditions are commands, and a failed step
    # unlocks nothing
    script = ew.launch_script()
    assert sum(1 for line in script.splitlines()
               if line.strip().startswith("need_marker ")) == 5

    # L11 — the pinned signature
    assert list(inspect.signature(ew.sampler_digest).parameters) == [
        "run", "tallies"]

    # L12 — the three checks, executed
    stored = np.array([[0.5, 0.25, 0.25]])
    drift = np.array([[0.5 + 1e-9, 0.25 - 1e-9, 0.25]])
    with pytest.raises(ew.ControlMismatch):
        ew.assert_identity_control("2019-08-09", ("m0",), drift, stored)
    with pytest.raises(ew.UntreatedMoved):
        ew.assert_untreated_unmoved("2019-08-09", ("m0",), drift, stored, ())
    with pytest.raises(ew.EvWidenError):
        ew.assert_pass_two_three_agree("2019-08-09", "m0", stored[0], drift[0])
    assert {"assert_identity_control", "assert_untreated_unmoved",
            "assert_pass_two_three_agree"} <= ew._calls_made(ew.Engine.fit)

    # L13 — the structural-zero guard, both sides
    for over in ({"delta": 1e-9},
                 {"e_min": 1.0, "incumbent_widened": True, "delta": 1e-9}):
        with pytest.raises(ew.UntreatedMoved):
            ew.assert_structural_zeros([{
                "match_id": "m", "e_min": 99.0, "delta": 0.0,
                "incumbent_widened": False, "treated": False, **over}])


@pinned
def test_the_freeze_block_is_harness_produced_and_round_trips(
        tmp_path, unrun_feasibility):
    """§8.3 step 2 asks its commit for the harness hashes, the schema identifier,
    the membership digests "recomputed by the harness's own code from the pinned
    artifacts", and an enumeration of every pre-freeze run.

    All four are rendered here, so the commit is a paste rather than a
    transcription — and the round trip is the test: the rendered block, dropped
    into a file, must make `harness_freeze_status` say frozen. A hash table the
    freeze checker cannot read is a hash table that freezes nothing.
    """
    block = ew.freeze_block()
    assert ew.SCHEMA_ID in block
    for name in ew.HARNESS_FILES:
        assert f"`{name}`" in block
        assert ew.sha256_file(ew.paths.REPO_ROOT / name) in block
    assert "| 85 |" in block and "| 52 |" in block and "| 51 |" in block
    assert "| 78 |" in block and "| 15 |" in block and "| 17 |" in block
    # §8.3 step 2's contents, all of them
    assert "Pre-freeze passes authorised under v3" in block
    assert "Prior history" in block
    # ...and §0.6's census record, bound by digest (§8.3)
    assert ew.FEASIBILITY_SHA256 in block
    escaped = "\\|"          # a `|` inside a markdown cell splits the row
    for key in ew.EXCLUDED_CELLS:
        assert key.replace("|", escaped) in block, key
        assert ew.EXCLUDED_CELL_DETAIL[key]["fixture"] in block
    assert "not the run this document preregisters" in block
    assert "the per-label treated census" in block          # §3.3's pin
    for digest in (ew.CORPUS_SHA256, ew.ARCHIVE_SHA256, ew.WALK_LEDGER_SHA256,
                   ew.CONFIG_SHA256, ew.REALISED_CONFIG_SHA256):
        assert digest in block                              # §0.1's four + one
    # ...and §8.5's report, every row, in the block itself
    assert "the conformance report of §8.5" in block.lower()
    for i in range(1, 19):
        assert f"| L{i} |" in block, i
    assert "| NO |" not in block

    assert all(name in block for name in
               ("--membership", "--freeze-block", "--power"))

    # THE ROUND TRIP IS NOT A PASTE ANY MORE (R2). v1's test dropped the
    # rendered block into a temporary file and demanded `harness_freeze_status`
    # say frozen; an uncommitted two-line paste satisfied that, which is not a
    # freeze. What is asserted instead is that the block a COMMIT would carry
    # binds the committed bytes.
    pasted = tmp_path / "prereg.md"
    pasted.write_text(block)
    with pytest.raises(ew.EvWidenError):
        ew.harness_freeze_status([pasted])
    assert ew.harness_freeze_status()["frozen"] is False
    import unittest.mock as mock

    with mock.patch.object(ew, "git_committed_bytes",
                           _as_if_committed(block)), \
            mock.patch.object(
                ew, "working_tree_bytes",
                lambda rel: (block.encode()
                             if rel == ew.paths.rel(ew.PREREG_PATH)
                             else (ew.paths.REPO_ROOT / rel).read_bytes())):
        got = ew.harness_freeze_status([ew.PREREG_PATH])
    assert got["frozen"] is True
    assert all(f["match"] for f in got["files"].values())


@pinned
def test_the_freeze_block_digests_are_the_membership_digests(unrun_feasibility):
    """The two must not be two computations of the same thing."""
    corpus, played, ledger = (ew.load_corpus(), ew.load_archive(),
                              ew.load_walk_ledger())
    from epl import baseline

    cells = ew.table_cells(baseline.load_matches(), played)
    digests = ew.membership_digests(corpus, played, ledger, table=cells)
    block = ew.freeze_block(corpus, played, ledger, cells)
    for value in digests["digests"].values():
        assert value in block


# ==========================================================================
# §8.6 — THE PUBLIC-SURFACE CLOSURE, and the seams it stands over
# ==========================================================================

def test_the_closure_refuses_a_seam_at_a_preregistered_target():
    """§8.6: "**No public surface of the harness accepts any parameter that can
    alter a frozen constant, inject an alternative implementation, attest a
    lifecycle state, or truncate a deciding population, when the target
    artifacts are pinned or the directories are the preregistered ones.**"

    The review's NEW-B1 through NEW-B4 were four instances of one defect, and
    v1 and v2's first harness each closed such leaks one at a time. This is the
    class, and it is one predicate: the guard refuses on the PINNED archive, on
    a frame DERIVED from it, on the pinned corpus, on any preregistered
    directory, and on a caller that named no directory at all — because the
    default is the preregistered run directory.
    """
    scratch = Path("/tmp") / "evwiden-not-preregistered"
    # a synthetic world in a directory of its own is exactly what §8.2
    # authorises the audit to use, and the guard lets it through
    assert ew.assert_seam_allowed("audit", played=_archive(), corpus=_corpus(),
                                  target=scratch)["allowed"] is True

    for kwargs in ({"target": None},
                   {"target": ew.EVWIDEN_DIR},
                   {"target": ew.EVWIDEN_DIR / "deeper" / "still"},
                   {"target": ew.TABLE_DIR},
                   {"target": ew.SEQUENCE_DIR},
                   {"target": ew.EVIDENCE_DIR}):
        with pytest.raises(ew.EvWidenError) as exc:
            ew.assert_seam_allowed("audit", played=_archive(), **kwargs)
        assert "preregistered directories" in str(exc.value)


@pinned
def test_the_closure_refuses_a_seam_on_the_pinned_and_near_real_artifacts():
    """§8.6, and §7.4's definition of synthetic made mechanical.

    NEW-B2: "a real-derived archive differing by one value is neither
    byte-identical pinned input nor v2-literal synthetic input, yet
    `is_pinned_archive` can classify it as non-pinned and allow it before
    freeze". §7.4 admits only frames whose every value is written literally in
    this module, so the ambiguous middle is REFUSED rather than allowed.
    """
    scratch = Path("/tmp") / "evwiden-not-preregistered"
    played = ew.load_archive()
    assert ew.archive_provenance(played) == "pinned"
    assert ew.archive_provenance(_archive()) == "synthetic"

    # one value changed: not the pinned archive by digest, and not synthetic
    # by ancestry either
    near_real = played.copy()
    near_real.loc[near_real.index[0], "fthg"] = int(
        near_real.loc[near_real.index[0], "fthg"]) + 7
    assert ew.archive_provenance(near_real) == "derived"
    assert ew.is_pinned_archive(near_real) is False
    assert ew.is_derived_from_pinned_archive(near_real) is True

    for frame in (played, near_real):
        with pytest.raises(ew.EvWidenError):
            ew.assert_seam_allowed("audit", played=frame, target=scratch)
        with pytest.raises(ew.EvWidenError) as exc:
            ew.assert_may_fit("audit", played=frame, directory=scratch)
        assert "pinned archive" in str(exc.value)

    # ...and the pinned CORPUS closes the same way
    with pytest.raises(ew.EvWidenError):
        ew.assert_seam_allowed("audit", corpus=ew.load_corpus(),
                               target=scratch)


def test_every_seam_the_review_named_asks_the_one_guard(tmp_path):
    """The surfaces, one by one, at a preregistered target.

    NEW-B1: `run_table`'s runner/parity. NEW-B2: `run_fits`'s fitter and
    engine, `run_parity_oracle`'s runner, `run_canary`'s runner. NEW-B3:
    `score_table`'s `mc` and `tallies`. NEW-B4: `merge`'s lifecycle Booleans.
    """
    corpus, played, ledger = _world()
    cells = _cells()

    def refuses(fn):
        with pytest.raises(ew.EvWidenError) as exc:
            fn()
        assert "public-surface closure" in str(exc.value), str(exc.value)[:200]

    refuses(lambda: ew.run_fits([], ew.EVWIDEN_DIR / "s.jsonl", corpus,
                                fitter=lambda *a, **k: {}))
    refuses(lambda: ew.run_table(cells, ew.TABLE_LEDGER,
                                 runner=_table_runner(),
                                 parity=_parity_for(cells)))
    refuses(lambda: ew.run_parity_oracle(cells, ew.TABLE_DIR / "parity.jsonl",
                                         runner=lambda c: {}))
    refuses(lambda: ew.run_canary(runner=lambda: {"PASS": True},
                                  target=ew.EVWIDEN_DIR))
    # ...and `score_table` no longer has a seam to refuse: v3 §8.6 consequence
    # 6 removed `mc=` and `tallies=` outright, because the guard over them was
    # keyed to `ledger_path` and a scratch path bought a caller real deciding
    # evidence (NB7)
    assert ew._no_parameter(ew.score_table, "mc", "tallies")
    refuses(lambda: ew.merge(shards=ew.SHARDS, harness_frozen=True))
    refuses(lambda: ew.merge(shards=ew.SHARDS, require_canaries=False))

    # ...and the same seams in a scratch directory on a synthetic world are
    # exactly what §8.2 authorises the audit to use
    assert ew.run_parity_oracle(cells, tmp_path / "parity.jsonl",
                                runner=lambda c: {
                                    "key": f"{c['season']}|{c['cutoff_label']}",
                                    "substantive_digest": "d"},
                                verbose=False)


def test_no_table_surface_carries_a_budget_it_could_be_given(tmp_path):
    """§2.3's closure reaches `n_sims`, and §8.6 makes production paths RESOLVE
    rather than accept: "there is no `n_sims`, `seed` or `chunk_size` parameter
    on this surface and there may not be one".

    The in-tree audit's finding was that §2.3 "names `n_sims` (20,000) in the
    closure by name" while `TableRunner`, `ParityRunner`, `run_table` and
    `simulate_arm` all accepted it and none of them called
    `assert_not_overridable`.
    """
    from epl import leaguesim, simretro

    frozen = ew.frozen_table_constants()
    assert frozen == {"n_sims": simretro.DEFAULT_N_SIMS,
                      "seed": simretro.SEED,
                      "chunk_size": leaguesim.DEFAULT_CHUNK_SIZE}
    assert frozen["n_sims"] == 20_000 and frozen["seed"] == 20260611
    for fn in (ew.TableRunner.__init__, ew.ParityRunner.__init__,
               ew.run_table, ew.simulate_arm):
        assert ew._no_parameter(fn, "n_sims", "seed", "chunk_size"), fn
    # ...and `e*` and the grid are refused where they still have keywords
    for call in (lambda: ew.run_fits([], tmp_path / "s.jsonl", None,
                                     e_star=ew.E_STAR + 1),
                 lambda: ew.run_fits([], tmp_path / "s.jsonl", None,
                                     grid=(1.0,)),
                 lambda: ew.estimand([], e_star=ew.E_STAR + 1)):
        with pytest.raises(ew.EvWidenError) as exc:
            call()
        assert "not overridable" in str(exc.value)


def test_limit_names_step_two_and_nothing_else(capsys):
    """§8.6's closure on truncation, and §2.4's refusal to thin the run.

    NEW-B1: "generic `--limit` can truncate the real step-3 population". §8.4
    step 2 is `--run --limit 1` and that is the only population the flag may
    name.
    """
    for argv in (["--limit", "2", "--run"], ["--limit", "0", "--run"],
                 ["--limit", "1", "--table"], ["--limit", "1", "--merge"],
                 ["--limit", "3", "--merge"]):
        assert ew.main(argv) == 2, argv
        assert "--limit" in capsys.readouterr().out


# ==========================================================================
# §8.2 pass 4 — the partial engine pass, EXECUTABLE
# ==========================================================================

def test_a_construction_only_engine_refuses_to_fit_before_it_reaches_dcfit(
        monkeypatch):
    """§8.2 pass 4, and the review's NEW-B5: the pass was authorised and
    unexecutable, because `Engine.__init__` called the guard and the guard
    refused the pinned archive while unfrozen.

    The mode is not a seam — it can only make the object LESS capable — and the
    reason the guard permits it is structural: `fit` refuses on the flag BEFORE
    it imports `dcfit` or touches the sampler. This test proves the stopping
    point by making `dcfit.fit_epl` explode if it is ever reached.
    """
    from epl import dcfit

    reached = []
    monkeypatch.setattr(dcfit, "fit_epl",
                        lambda *a, **k: reached.append(True))

    post = _FakePosterior()
    corpus, _ = _engine_world(post)
    engine = _bare_engine(post, corpus, monkeypatch=monkeypatch)
    engine.can_fit = False
    with pytest.raises(ew.EvWidenError) as exc:
        engine.fit(_engine_point(corpus))
    assert "cannot fit" in str(exc.value)
    assert "§8.2" in str(exc.value)
    assert reached == []            # the sampler was never reached

    # ...and the stopping point is STRUCTURAL where §8.2 says it is: the
    # refusal precedes the `dcfit` import, so the pass cannot reach the
    # sampler's MODULE either. The in-tree audit's finding 7 was that v2 made
    # exactly this claim while the import ran at entry and `can_fit` was tested
    # after it — a false sentence about a stopping point.
    import inspect

    source = inspect.getsource(ew.Engine.fit)
    assert source.index("if not self.can_fit") < source.index("import dcfit")


@pinned
def test_the_partial_engine_pass_runs_and_leaves_the_store_untouched():
    """§8.2 pass 4, executed on the REAL archive while unfrozen — which is the
    whole point of the finding: "`Engine(corpus, played, directory=<scratch>)`
    and `Engine(corpus, played)` both raise EvWidenError", so the enumeration
    named a pass no command could run.

    It runs construction, `fit_points`, the enlarged set, `assert_cutoff_clean`
    and `assert_point_in_time`, stops before `dcfit.fit_epl`, and the shared
    point-in-time store is byte-identical afterwards.
    """
    store = ew.paths.STORE_DIR / ew.STORE_TABLE_PARQUET
    if not store.exists():
        pytest.skip("the shared point-in-time store is not on this machine")
    before = (ew.sha256_file(store), store.stat().st_mtime_ns)

    out = ew.partial_engine_pass()
    assert out["opening"] == ew.PARTIAL_ENGINE_OPENING == "2019-08-09"
    assert out["stopped_before"] == "epl.dcfit.fit_epl"
    assert out["fit_refused"] is True
    assert out["cutoff_clean"] is True and out["point_in_time"] is True
    assert out["store_unchanged"] is True
    # §2.3 names the opening's own sets: ledger incumbent {sheffield_united},
    # the §2.1 union adding exactly {aston_villa, norwich}
    assert out["added"] == ["aston_villa", "norwich"], out["added"]
    assert (ew.sha256_file(store), store.stat().st_mtime_ns) == before


# ==========================================================================
# §0.6's census — read-only, digest-bound, and the surface that produced it
# CLOSED. v3 §8.2 authorises no pre-freeze pass that fits or simulates.
# ==========================================================================

def test_v3_carries_no_pass_that_fits_or_simulates(tmp_path, monkeypatch):
    """v3 §8.2: "This document authorises no pre-freeze pass that fits or
    simulates. [...] the question it existed to answer has been answered."

    The review's P5-B2 found four holes in v2's pass — a mutable permission
    set, mutable pass state, a forgeable/deletable record, and a runner that
    carried its permission out of the closed context. Deleting the surface
    closes all four at once, and this test is what says the surface is gone
    rather than merely unused."""
    for gone in ("parity_feasibility_pass", "parity_feasibility_census",
                 "FEASIBILITY_SURFACES", "_FEASIBILITY", "FEASIBILITY_NOTE",
                 "FEASIBILITY_ROWS_NAME", "_feasibility_permits"):
        assert not hasattr(ew, gone), gone
        assert gone not in ew.__all__
    assert ew.FEASIBILITY_SURFACE_CLOSED is True
    # ...and the CLI carries no way to run one
    source = Path(ew.__file__).read_text()
    assert "--parity-feasibility" not in source.replace(
        "#: `--parity-feasibility`, no", "")
    assert "--quarantine" not in source
    # PRE_FREEZE_RUNS is six, all read-only; pass 7 is HISTORY and separate
    assert len(ew.PRE_FREEZE_RUNS) == 6
    assert not any("feasibility" in r.lower() for r in ew.PRE_FREEZE_RUNS)
    assert len(ew.PRIOR_PASSES) == 1
    assert "v2 §8.2 pass 7" in ew.PRIOR_PASSES[0]
    assert "2026-08-28" in ew.PRIOR_PASSES[0]
    # ...and a ParityRunner has no cached feasibility permission to carry
    assert not hasattr(ew.ParityRunner, "_under_feasibility")


def _census_record(**over):
    """§0.6's record, as `feasibility_status` has to read it. Literal values."""
    priceable = [k for k in ew._v3_priceable_keys()]
    rec = {"schema": "epl-evwiden-2", "completed": True, "feasible": False,
           "cells_expected": 35, "cells_attempted": 35, "error": None,
           "arm": "dc_native", "priceable": priceable,
           "unpriceable": [{"key": k,
                            "refusal_kind": "excluded_mass_ceiling"}
                           for k in ew.EXCLUDED_CELLS],
           "n_unpriceable": 3}
    rec.update(over)
    return rec


def _plant_census(tmp_path, monkeypatch, rec, *, bind=True):
    """Write a census record and (by default) re-pin the digest onto it."""
    path = tmp_path / "evwiden_parity_feasibility.json"
    path.write_text(json.dumps(rec, indent=2))
    monkeypatch.setattr(ew, "FEASIBILITY_RECORD", path)
    if bind:
        raw = path.read_bytes()
        monkeypatch.setattr(ew, "FEASIBILITY_SHA256",
                            __import__("hashlib").sha256(raw).hexdigest())
        monkeypatch.setattr(ew, "FEASIBILITY_BYTES", len(raw))
    return path


@pinned
def test_the_census_record_is_read_and_checked_never_trusted(tmp_path,
                                                             monkeypatch):
    """v3 §0.1: the record is a PIN, not a citation. §8.3 binds its digest into
    the freeze block "because a scope that rests on an unhashed local file
    rests on nothing"."""
    _plant_census(tmp_path, monkeypatch, _census_record())
    status = ew.feasibility_status()
    assert status["ok"] is True and status["present"] is True
    assert status["n_priceable"] == 32 and status["n_unpriceable"] == 3
    assert status["unpriceable"] == sorted(ew.EXCLUDED_CELLS)
    assert ew.assert_feasibility_permits_a_freeze()["ok"] is True


@pinned
def test_a_census_that_is_not_the_census_scopes_nothing(tmp_path, monkeypatch):
    """v3 §8.3, and the condition INVERTS from v2's.

    > v2's block refused over an *infeasible* census, which was the right
    > refusal for a document claiming thirty-five. This document claims
    > thirty-two **because** three cells are unpriceable, so the condition
    > inverts: the block refuses unless the record says exactly that, cell for
    > cell. A census that suddenly prices all thirty-five is as much a refusal
    > as one that prices thirty-one.
    """
    # (a) absent
    monkeypatch.setattr(ew, "FEASIBILITY_RECORD",
                        tmp_path / "nothing-here.json")
    assert ew.feasibility_status()["ok"] is False
    with pytest.raises(ew.FeasibilityRecordMismatch) as exc:
        ew.assert_feasibility_permits_a_freeze()
    assert ew.FEASIBILITY_ABSENT in str(exc.value)

    # (b) present but not the pinned bytes — the digest is the whole point
    path = _plant_census(tmp_path, monkeypatch, _census_record(), bind=False)
    monkeypatch.setattr(ew, "FEASIBILITY_SHA256", "0" * 64)
    monkeypatch.setattr(ew, "FEASIBILITY_BYTES", path.stat().st_size)
    with pytest.raises(ew.FeasibilityRecordMismatch) as exc:
        ew.assert_feasibility_permits_a_freeze()
    assert "digest" in str(exc.value)

    # (c) did not complete
    _plant_census(tmp_path, monkeypatch,
                  _census_record(completed=False, cells_attempted=12))
    with pytest.raises(ew.FeasibilityRecordMismatch) as exc:
        ew.assert_feasibility_permits_a_freeze()
    assert "did NOT complete" in str(exc.value)

    # (d) ALL THIRTY-FIVE priced — v2's block would have been delighted; v3
    #     refuses, because this document is scoped to 32 by measurement
    every = [f"{s}|{lab}" for s in __import__(
        "epl.simretro", fromlist=["x"]).SEASONS
        for lab in __import__("epl.simretro", fromlist=["x"]).COMPARISON_CUTOFFS]
    _plant_census(tmp_path, monkeypatch,
                  _census_record(feasible=True, priceable=every,
                                 unpriceable=[], n_unpriceable=0))
    with pytest.raises(ew.FeasibilityRecordMismatch) as exc:
        ew.assert_feasibility_permits_a_freeze()
    assert "35 priceable" in str(exc.value)

    # (e) one cell short of the 32
    _plant_census(tmp_path, monkeypatch,
                  _census_record(priceable=ew._v3_priceable_keys()[:-1]))
    with pytest.raises(ew.FeasibilityRecordMismatch):
        ew.assert_feasibility_permits_a_freeze()


@pinned
def test_the_freeze_block_binds_the_census_digest_and_refuses_without_it(
        tmp_path, monkeypatch):
    """v3 §8.3: the block carries "the SHA-256 and byte size of §0.6's
    feasibility census record", and refuses to render while the record is not
    the record."""
    monkeypatch.setattr(ew, "FEASIBILITY_RECORD", tmp_path / "gone.json")
    with pytest.raises(ew.FeasibilityRecordMismatch):
        ew.freeze_block()
    assert "assert_feasibility_permits_a_freeze" in ew._calls_made(
        ew.freeze_block)


def test_the_document_and_the_harness_agree_on_the_census():
    """v3 §0.6's table is the harness's constants, and the three excluded cells
    are named in both with the same fixtures and the same measured masses."""
    if not PREREG_V3.exists():
        pytest.skip("the preregistration is committed on the machine that "
                    "wrote it")
    text = PREREG_V3.read_text()
    for key in ew.EXCLUDED_CELLS:
        season, label = key.split("|")
        detail = ew.EXCLUDED_CELL_DETAIL[key]
        assert f"{season} {label}" in text, key
        assert detail["fixture"] in text, key
        assert str(detail["excluded_mass"]) in text, key
    assert ew.FEASIBILITY_SHA256 in text
    assert f"{ew.FEASIBILITY_BYTES:,}" in text
    # ...and the census table's own numerals
    for numeral in ("32 priceable", "15 treated", "17 untouched"):
        assert numeral in text, numeral

# ==========================================================================
# §5.4 — the joint draw, and the de-paired one it must disagree with
# ==========================================================================

def _per_cell_unanimity(cells, *, point_verdict):
    """§5.4's rule with the joint draw DE-PAIRED — the audit's seed (k)."""
    from epl import simmetrics

    cells = list(cells)
    mw6 = [c for c in cells if str(c["cutoff_label"]) == ew.MW6_LABEL]
    n_particles = int(np.asarray(cells[0]["control"]).shape[0])
    seasons = [str(c["season"]) for c in mw6]
    rng = np.random.default_rng(ew.UNANIMITY_SEED)
    verdicts = []
    for _ in range(ew.UNANIMITY_K):
        deltas = {}
        for cell in cells:
            picked = rng.integers(0, n_particles, n_particles)
            scores = {}
            for arm in ("control", "treatment"):
                m = np.asarray(cell[arm], dtype=float)[picked].sum(axis=0)
                m = m / m.sum(axis=1, keepdims=True)
                scores[arm] = float(simmetrics.trps(m, cell["positions"],
                                                   spans=cell["spans"]))
            deltas[str(cell["key"])] = scores["treatment"] - scores["control"]
        verdicts.append(ew.iv_c_verdict([deltas[str(c["key"])] for c in mw6],
                                        seasons))
    return verdicts


def test_the_unanimity_draw_is_joint_and_a_per_cell_one_disagrees():
    """§5.4: "draw **one** joint particle resample `picked_k` and apply it to
    **all thirty tallies** exactly as §5.2 applies its own draw". §10 makes
    "an MC estimator that is not §5's jointly-resampled, tie-aware estimator" an
    invalidation.

    The in-tree audit found this untested and PROVED it: making the K = 200
    resample per-cell instead of joint left 241 tests passing, because the
    rule's only test used ZERO-VARIANCE tallies, under which every resample is
    identical and the joint/per-cell distinction is invisible. On JITTERED
    tallies the two constructions are different rules, and this is the test that
    says so.

    (The same property IS tested for `paired_mc_bootstrap` — see
    `test_the_paired_bootstrap_applies_one_index_to_every_tally` — so the gap
    was specific to P5.)
    """
    cells = [dict(c, season=f"20{19 + i}/2{i}")
             for i, c in enumerate(_mc_cells(n=7, jitter=3))]
    joint = ew.unanimity(cells, point_verdict=True)
    depaired = _per_cell_unanimity(cells, point_verdict=True)
    assert len(joint["verdicts"]) == len(depaired) == ew.UNANIMITY_K
    assert list(joint["verdicts"]) != list(depaired)


def test_the_gate_refuses_a_unanimity_run_it_cannot_verify():
    """§5.4, and the review's NEW-B3: `table_gate` trusted "any truthy
    `mc.unanimity` with `fired=False`" and validated "neither `K=200`, seed, 200
    verdicts, nor dissent consistency", so a fabricated `k=1` object could
    resolve PASS.

    The check is one-directional, like everything else in §5.4: an unverifiable
    run is UNRESOLVED, exactly as an absent one is.
    """
    good = _unanimous(False)
    assert ew.unanimity_is_valid(good, point_verdict=False)["valid"] is True
    for bad, why in (
            (None, "no unanimity run"),
            (dict(good, k=1), "§5.4 freezes K"),
            (dict(good, seed=1), "§5.4 freezes"),
            ({k: v for k, v in good.items() if k != "verdicts"}, "verdicts"),
            (dict(good, verdicts=good["verdicts"][:10]), "verdicts"),
            (dict(good, dissenting=4), "actually disagree"),
            (dict(good, fired=True), "against"),
    ):
        checked = ew.unanimity_is_valid(bad, point_verdict=False)
        assert checked["valid"] is False, bad
        assert why in checked["why"], (bad, checked["why"])
    # ...and the gate's own point verdict has to be the one the run was scored
    # against
    assert ew.unanimity_is_valid(good, point_verdict=True)["valid"] is False


# ==========================================================================
# §3.2 — the identity control, on the openings that carry treated fixtures
# ==========================================================================

def test_the_engine_control_refuses_a_drift_where_the_union_adds_somebody(
        monkeypatch):
    """The in-tree audit's finding, and the site §10 names.

    Loosening `Engine.fit`'s exact comparison DID turn a test red — but with
    `CanaryFailed` from the identity-canary branch, not `ControlMismatch`,
    because that test's block had an empty `added` set. The identity-canary
    branch only runs where the §2.1 union adds nobody: 16 of the 78 openings.
    On the 62 that carry treated fixtures the site §10 names — "The identity
    control's tolerance is widened after a mismatch, ANYWHERE" — was uncovered.

    This is that opening: a NON-EMPTY `added` set, and a 1e-9 drift in the
    corpus row. `Engine.fit` must refuse with `ControlMismatch`.
    """
    post = _FakePosterior()
    corpus, _ = _engine_world(post)
    corpus = corpus.copy()
    corpus.loc[corpus.index[0], "dc_home"] = float(
        corpus.loc[corpus.index[0], "dc_home"]) + 1e-9
    corpus.loc[corpus.index[0], "dc_draw"] = float(
        corpus.loc[corpus.index[0], "dc_draw"]) - 1e-9
    corpus.loc[corpus.index[0], "dc_rps"] = float(score_mod.rps(
        np.array([[corpus.loc[corpus.index[0], c]
                   for c in ("dc_home", "dc_draw", "dc_away")]]),
        np.array([int(corpus.loc[corpus.index[0], "y"])]))[0])

    # `a` is evidence-thin, so the §2.1 union ADDS it: `added` is non-empty and
    # the identity-canary branch does not run.
    engine = _bare_engine(post, corpus, monkeypatch=monkeypatch,
                          evidence={"2019/20|W01": {"a": 0.5, "b": 50.0}})
    with pytest.raises(ew.ControlMismatch) as exc:
        engine.fit(_engine_point(corpus))
    assert "EXACT equality at the corpus's eight decimals" in str(exc.value)


# ==========================================================================
# §8.4 — the failed step, the once-written marker, the durable publication
# ==========================================================================

def test_a_failed_step_marker_unlocks_nothing_and_names_the_failure(
        tmp_path, monkeypatch):
    """§8.4, and the review's NEW-B8: "a failed first real-fit canary therefore
    leaves no durable result or marker and can be retried, creating an
    outcome-dependent retry/file-drawer channel"."""
    monkeypatch.setattr(ew, "SEQUENCE_DIR", tmp_path / "sequence")
    ew.write_sequence_marker(ew.SEQUENCE_STEPS[0], complete=False,
                             produced={"failure": "the canary did not pass"})
    marker = ew.read_sequence_marker(ew.SEQUENCE_STEPS[0])
    assert marker["complete"] is False
    with pytest.raises(ew.SequenceViolation) as exc:
        ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=True)
    assert "RAN AND FAILED" in str(exc.value)
    assert "new dated pre-freeze note" in str(exc.value)


def test_a_marker_is_written_once_and_re_verified_afterwards(tmp_path,
                                                             monkeypatch):
    """§8.4, and the review's NEW-B7: the markers are MANIFEST members, and the
    publication pass rewrote `step4_merge.json` after §9.3 had hashed it.

    A second write of the SAME product re-verifies and returns the marker
    unchanged, bytes and all; a second write of a DIFFERENT one refuses.
    """
    monkeypatch.setattr(ew, "SEQUENCE_DIR", tmp_path / "sequence")
    first = ew.write_sequence_marker(ew.SEQUENCE_STEPS[3],
                                     produced={"n_fits": 78})
    path = ew.sequence_marker_path(ew.SEQUENCE_STEPS[3])
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    again = ew.write_sequence_marker(ew.SEQUENCE_STEPS[3],
                                     produced={"n_fits": 78})
    assert again == first
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    with pytest.raises(ew.SequenceViolation) as exc:
        ew.write_sequence_marker(ew.SEQUENCE_STEPS[3], produced={"n_fits": 77})
    assert "written once" in str(exc.value)


def test_every_sequence_marker_is_a_manifest_member():
    """§9.3, and why the once-written rule exists: publication hashes them."""
    for step in ew.SEQUENCE_STEPS:
        assert f"data/epl/fit/evwiden/sequence/{step}.json" in ew.MANIFEST_PATHS


def test_a_failing_results_canary_carries_its_record_on_the_refusal():
    """§8.4 step 1: "`PASS: false` on any leg stops the experiment and **the
    failure publishes**" — and it publishes BEFORE the raise, which needs the
    record to travel on the exception."""
    with pytest.raises(ew.CanaryFailed) as exc:
        ew.run_canary(lambda: {"PASS": False,
                               "max_abs_diff_before_cutoff": 0.5},
                      played=_archive(),
                      target=Path("/tmp") / "evwiden-not-preregistered",
                      directory=Path("/tmp") / "evwiden-not-preregistered")
    assert getattr(exc.value, "record", None)["PASS"] is False
    assert exc.value.record["max_abs_diff_before_cutoff"] == 0.5


def _failing_canary(monkeypatch, tmp_path, *, frozen: bool):
    """`--canary` driven to its FAILURE path, with nothing pinned underneath.

    The four real fits are `_run_all_canaries`' business and this is not a test
    of them: what is under test is the two writes `main` owes §8.4 step 1 before
    the refusal reaches the process.
    """
    failed = {"schema": ew.SCHEMA_ID, "cutoff": "2019-08-09",
              "results": {"PASS": False,
                          "max_abs_diff_before_cutoff": 0.5},
              "PASS": False}
    exc = ew.CanaryFailed("the results canary moved a fixture before its cutoff")
    exc.record = failed

    def _boom(*a, **k):
        raise exc

    monkeypatch.setattr(ew, "_run_all_canaries", _boom)
    monkeypatch.setattr(ew, "load_corpus", lambda *a, **k: None)
    monkeypatch.setattr(ew, "load_archive", lambda *a, **k: None)
    monkeypatch.setattr(ew, "load_walk_ledger", lambda *a, **k: None)
    monkeypatch.setattr(ew, "_frozen_now", lambda: frozen)
    monkeypatch.setattr(ew, "read_sequence_marker", lambda step: None)
    # `main` turns every `EvWidenError` into `STOP: …` and exit code 2 — the
    # refusal still reaches the process, and the publication has to have
    # happened before it did.
    assert ew.main(["--canary", "--dir", str(tmp_path)]) == 2


def test_a_failed_canary_publishes_its_record_before_the_refusal_is_raised(
        tmp_path, monkeypatch):
    """§8.4 step 1: "`PASS: false` on any leg stops the experiment and **the
    failure publishes**."

    The in-tree audit's seed (x): deleting `main`'s entire publish-before-raise
    block left the widening suite at 265 passed, because the only test of the
    area asserted that the record TRAVELS on the exception and never drove
    `main`'s failure path at all. A failed canary that leaves no durable
    artifact can simply be attempted again, which is §4.4's file-drawer channel
    — and §8.7 forbids repairing a hashed file after the first real fit, so an
    untested guarantee frozen in cannot be repaired afterwards.

    THIS TEST GOES RED IF THE PUBLICATION IS DELETED: it reads `canary.json`
    off the disk after the refusal, not the exception.
    """
    _failing_canary(monkeypatch, tmp_path, frozen=False)
    published = json.loads((tmp_path / ew.CANARY_NAME).read_text())
    assert published["PASS"] is False
    assert published["results"]["PASS"] is False
    assert "CanaryFailed" in published["failure"]
    assert published["results_canary_run"] is True
    assert published["schema"] == ew.SCHEMA_ID


def test_a_failed_canary_marks_step_one_incomplete_before_the_refusal(
        tmp_path, monkeypatch):
    """The other half of the same clause, under a freeze: the failure is a
    DURABLE marker as well as a record, and `require_sequence` refuses on it
    exactly as it refuses on an absent one — "a failure marker unlocks
    nothing".

    The marker write is captured rather than performed: §8.4's markers live at
    one fixed path under `data/epl/fit/evwiden/sequence/`, and this module's
    autouse fixture holds that tree untouched.
    """
    written: list[dict] = []
    monkeypatch.setattr(
        ew, "write_sequence_marker",
        lambda step, *, produced=None, complete=True: written.append(
            {"step": step, "produced": produced, "complete": complete}))
    _failing_canary(monkeypatch, tmp_path, frozen=True)

    assert [m["step"] for m in written] == [ew.SEQUENCE_STEPS[0]]
    marker = written[0]
    assert marker["complete"] is False
    assert "CanaryFailed" in marker["produced"]["failure"]
    # ...and what it names is the record that is ON DISK, by its digest
    canary = tmp_path / ew.CANARY_NAME
    assert marker["produced"]["canary"] == ew.paths.rel(canary)
    assert marker["produced"]["digest"] == ew.sha256_file(canary)


def test_the_script_writes_no_launcher_before_the_freeze():
    """§8.2's enumeration is complete and none of its entries writes inside the
    repository; the review found `--script` writing one under `data/` with no
    freeze anywhere. The launcher is a POST-freeze artifact."""
    with pytest.raises(ew.EvWidenError) as exc:
        ew.write_launch_script()
    assert "before" in str(exc.value)
    assert not (ew.EVWIDEN_DIR / ew.LAUNCH_NAME).exists()


# ==========================================================================
# §8.6 — the guard's remaining conditions
# ==========================================================================

def test_the_freeze_guard_reads_the_committed_conformance_report():
    """§8.6 condition (5), and the review's NEW-B4: "`freeze_block(
    check_implementation=False)` renders despite a red conformance report [...]
    The later freeze guard does not validate report greenness."

    The bypass is gone; this is the other half — the guard reads the report back
    out of the committed block, so a block that was somehow rendered red cannot
    establish the freeze state either.
    """
    import inspect

    assert ew._no_parameter(ew.freeze_block, "check_implementation",
                            "power", "pre_freeze_runs")
    assert "assert_implements_document" in ew._calls_made(ew.freeze_block)
    assert "implementation_report" not in ew._calls_made(ew.freeze_block)

    header = "| row | § | obligation | green |"
    green = "\n".join([header, "|---|---|---|---|",
                       "| L1 | §2.3 | both arms | yes |",
                       "| L2 | §4.1 | per horizon | yes |", ""])
    red = green.replace("| L2 | §4.1 | per horizon | yes |",
                        "| L2 | §4.1 | per horizon | NO |")
    assert ew._recorded_conformance(green) == {"L1": True, "L2": True}
    assert ew._recorded_conformance(red) == {"L1": True, "L2": False}
    assert ew._recorded_conformance("no table here") == {}
    assert inspect.isfunction(ew._recorded_conformance)


def test_a_first_fit_record_missing_an_identity_field_is_unverified(
        tmp_path, monkeypatch):
    """§8.6 fixes the record's contents, and NB5's finding was that the guard
    "conditionally accepts missing prereg/blob fields" — so a record with the
    fields stripped out passed every check by carrying none of them."""
    monkeypatch.setattr(ew, "FIRST_FIT_JSON", tmp_path / "first.json")
    monkeypatch.setattr(ew, "FIRST_FIT_WITNESS",
                        tmp_path / "first_witness.jsonl")
    full = ew.record_first_real_fit(where="a test")
    assert set(full) >= {"schema", "at", "where", "prereg", "prereg_blob",
                         "commit", "harness"}
    for field in ("schema", "at", "where", "prereg", "prereg_blob", "commit",
                  "harness"):
        ew.FIRST_FIT_JSON.write_text(json.dumps(
            {k: v for k, v in full.items() if k != field}))
        with pytest.raises(ew.FreezeStateUnverified) as exc:
            ew.assert_no_hashed_file_moved()
        assert field in str(exc.value) or "schema" in str(exc.value), field


def test_the_first_fit_record_is_written_at_the_fit_and_not_at_the_check():
    """§8.6: "the UTC instant of the first real fit". The review found the
    record "written during permission checking, before an actual fit begins".

    `assert_may_fit` is the permission check and no longer writes it; the call
    sites that are about to enter the sampler do, immediately before they do.
    """
    assert "record_first_real_fit" not in ew._calls_made(ew.assert_may_fit)
    for fn in (ew.Engine.fit, ew.run_canary,
               ew.ParityRunner.__call__, ew.TableRunner.__call__):
        assert "record_first_real_fit" in ew._calls_made(fn), fn


def test_a_simulation_that_fits_nothing_records_no_first_real_fit():
    """The adjudication of 2026-08-29, F7 (IMP-FIRST-FIT-TIMESTAMP).
    "`simulate_arm` records a 'first real fit' before a simulation that performs
    no fit."

    F7: "record at true fit sites, immediately before sampler entry". §8.6's
    record is "the UTC instant of the FIRST REAL FIT", and `simulate_arm` is the
    one call into `epl.leaguesim.simulate` — it draws seasons from a posterior
    somebody else fitted. A fit clock that a non-fitting surface can start is
    recording something other than what it names, and on the table leg it would
    always be started by the wrong one of the two: `TableRunner` fits and then
    simulates, so the instant would be the simulation's, not the fit's.
    """
    assert "record_first_real_fit" not in ew._calls_made(ew.simulate_arm)
    # it is still GATED — F7 moves the clock, it does not open the surface
    assert "assert_may_fit" in ew._calls_made(ew.simulate_arm)
    assert "simulate" in ew._calls_made(ew.simulate_arm)


def test_the_guard_demands_equality_on_the_membership_digests():
    """§8.6 condition (3) asks that the recorded digests "equal a fresh
    recomputation". The superseded reader scraped every backticked 64-hex string
    in the block — the harness hashes and the pinned artifact digests among
    them — so the check could only ever be a containment."""
    block = "\n".join([
        "| file | lines | SHA-256 |",
        "|---|---:|---|",
        f"| `epl/evwiden.py` | 1 | `{'a' * 64}` |",
        "",
        "| membership | count | SHA-256 of the canonical serialisation |",
        "|---|---:|---|",
        f"| the thin fixtures (§2.3) | 85 | `{'b' * 64}` |",
        f"| the treated fixtures (§2.3) | 52 | `{'c' * 64}` |",
        "",
        "| pinned artifact | SHA-256 |",
        f"| `data/epl/matches.parquet` | `{'d' * 64}` |",
    ])
    recorded = ew._recorded_membership_digests(block)
    assert recorded == {"b" * 64, "c" * 64}       # not the harness hash, not
    assert "a" * 64 not in recorded               # the pinned artifact digest
    assert "d" * 64 not in recorded


def test_the_real_engine_fits_identity_canary_branch_is_exercised(monkeypatch):
    """§7.3's identity canary, in the PRODUCTION branch — the audit's A2.

    "The production identity-canary branch is not directly asserted; explicit
    identity-canary tests still use `_stub_fitter`. Replacing the production
    branch with a constant PASS can leave the suite green."

    On 16 of the 78 openings the §2.1 union adds nobody, and `Engine.fit`'s
    pass 2 IS the canary there: Arm A must be byte-identical to the corpus.
    This drives the real method with an evidence table that adds nobody and a
    posterior whose widened pass moves anyway.
    """
    post = _FakePosterior()
    corpus, _ = _engine_world(post)
    # every club is evidence-rich, so `enlarged - incumbent` is empty and the
    # canary branch — and only the canary branch — decides the fit
    engine = _bare_engine(post, corpus, monkeypatch=monkeypatch,
                          evidence={"2019/20|W01": {"a": 50.0, "b": 50.0}})
    out = engine.fit(_engine_point(corpus))
    assert out["identity_canary"] is True
    assert out["provisional_enlarged"] == out["provisional_incumbent"]

    # ...and where the union DOES add a club the branch does not run at all,
    # which is the other half of "on 16 of the 78 blocks the §2.1 union adds
    # nobody, and pass 2 IS that canary".
    treated_engine = _bare_engine(post, corpus, monkeypatch=monkeypatch,
                                  evidence={"2019/20|W01": {"a": 0.5,
                                                            "b": 50.0}})
    assert treated_engine.fit(_engine_point(corpus))["identity_canary"] is None

    # WHAT THE BRANCH CAN AND CANNOT CATCH, stated rather than assumed. Its
    # refusal is unreachable while the two checks before it hold: with an empty
    # `added` every fixture is untreated, so `assert_untreated_unmoved` has
    # already required Arm A to equal Arm B, and `assert_identity_control` has
    # already required Arm B to equal the corpus. The branch is a restatement
    # whose force comes from those two, and that is exactly why §8.5's L12
    # tests THEM directly rather than resting on this canary. A drift that
    # would move Arm A is therefore caught, but by `UntreatedMoved`.
    drifted = np.array([[0.5, 0.25, 0.25]])
    with pytest.raises(ew.UntreatedMoved):
        ew.assert_untreated_unmoved("2019-08-10", ("m0",),
                                    drifted + 1e-9, drifted, ())


def test_an_empty_marker_is_not_a_completed_step(tmp_path, monkeypatch):
    """§8.4, and NB6: "`{}` is accepted because `require_sequence` permits
    missing/null `freeze_commit` and validates no step/schema/hashes/product"."""
    monkeypatch.setattr(ew, "SEQUENCE_DIR", tmp_path / "sequence")
    path = ew.sequence_marker_path(ew.SEQUENCE_STEPS[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    with pytest.raises(ew.SequenceViolation) as exc:
        ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=True)
    assert "An empty JSON object is not a completed step" in str(exc.value)

    path.unlink()
    good = ew.write_sequence_marker(ew.SEQUENCE_STEPS[0], produced={"a": 1})
    assert ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=True)["PASS"]

    # a marker that names another document, another step, or harness bytes
    # that are not the current ones is not this run's marker either
    for over, why in ((("schema", "epl-evwiden-1"), "another document's run"),
                      (("step", ew.SEQUENCE_STEPS[3]), "another step's slot"),
                      (("harness", {n: "0" * 64 for n in ew.HARNESS_FILES}),
                       "not the current bytes")):
        path.write_text(json.dumps(dict(good, **{over[0]: over[1]})))
        with pytest.raises(ew.SequenceViolation) as exc:
            ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=True)
        assert why in str(exc.value), over


def test_the_sequence_check_cannot_be_turned_off_under_the_freeze(monkeypatch):
    """§8.6 closes "attest a lifecycle state", and `enforce=False` is that
    attestation: it says §8.4's five steps do not apply to this call.

    It exists for the pre-freeze audit, where `enforce=None` DERIVES the same
    answer because there is no run for the markers to describe. Under the freeze
    there is one, and no caller turns the sequence off for it.
    """
    assert ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=False)["PASS"]
    monkeypatch.setattr(ew, "_frozen_now", lambda: True)
    with pytest.raises(ew.SequenceViolation) as exc:
        ew.require_sequence(ew.SEQUENCE_STEPS[1], enforce=False)
    assert "attesting a lifecycle state" in str(exc.value)


def test_the_seams_of_the_closure_ask_the_guard_by_effect(tmp_path):
    """§8.6: "any parameter with one of those four effects is closed on those
    terms, **named here or not**."

    The closure round applied it at six call sites, and the review's Part on
    unguarded parameters read the rest off the module by signature. These are
    those parameters. Each is legitimate where §8.2 says an audit run is
    legitimate — synthetic artifacts, a directory of its own — and refused at the
    preregistered ones.
    """
    # publishing §9's evidence without §9.3's 52-member manifest (P5-B7)
    with pytest.raises(ew.EvWidenError) as exc:
        ew.write_evidence({}, manifest=False)
    assert "public-surface closure" in str(exc.value)
    with pytest.raises(ew.EvWidenError):
        ew.write_evidence({}, directory=ew.EVIDENCE_DIR,
                          require_manifest_complete=False)
    # ...and the same call into a scratch directory is an audit, and runs
    assert ew.write_evidence({"schema": ew.SCHEMA_ID}, directory=tmp_path,
                             manifest=False)["widening.json"]

    # a caller-supplied cell census, and §9.3's manifest validation turned off
    with pytest.raises(ew.EvWidenError) as exc:
        ew.load_table_ledger(ew.TABLE_LEDGER, expected=[])
    assert "truncate a deciding population" in str(exc.value)
    if PINNED_ARCHIVE.exists():
        # ...and the census the PRODUCTION merge derives and passes is §3.3's
        # own, so the closure does not refuse the run it exists to protect
        from epl import baseline

        cells = ew.table_cells(baseline.load_matches())
        with pytest.raises(ew.MergeIncomplete):      # empty ledger, not a seam
            ew.load_table_ledger(ew.TABLE_LEDGER, expected=cells)
    with pytest.raises(ew.EvWidenError):
        ew.verify(evidence=ew.EVIDENCE_JSON, check_manifest=False)

    # an injected fitter in §7.3's identity canary, against the PINNED corpus
    if PINNED_CORPUS.exists():
        with pytest.raises(ew.EvWidenError):
            ew.identity_canary(lambda *a, **k: {}, ew.FitPoint(
                cutoff="2019-08-09", season="2019/20", block="2019/20|W01",
                match_ids=()), ew.load_corpus())

    # an alternate point-in-time store root inside the preregistered tree.
    # (v3 §8.6 consequence 5 narrowed the tree from all of the SHARED
    # `paths.FIT_DIR` to this experiment's own artifacts — P5-I2 — so the
    # target here is one of them rather than an unrelated neighbour.)
    with pytest.raises(ew.EvWidenError):
        ew.read_only_store(root=ew.EVWIDEN_DIR / "store")

    # the poison bypass is not a parameter at all: §7.1 makes a poison row
    # ShardFailed and §2.4 makes a poisoned shard unscorable
    assert ew._no_parameter(ew.load_ledger, "allow_poison")
    poisoned = tmp_path / ew.shard_name(0, 1)
    poisoned.write_text(json.dumps({"poison": True, "error_type": "FitFailed",
                                    "error": "x", "cutoff": "2019-08-09"})
                        + "\n")
    with pytest.raises(ew.ShardFailed):
        ew.load_ledger(poisoned)
    assert ew.completed_keys(poisoned) == set()

    # the generated launcher takes no interpreter (P5-B6)
    assert ew._no_parameter(ew.launch_script, "python")
    assert ew._no_parameter(ew.write_launch_script, "python", "kwargs")
    assert ew.LAUNCH_PYTHON in ew.launch_script(tmp_path)

    # ...and the ordering helper is not a public surface (P5-B5)
    assert "run_cell_arms" not in ew.__all__


def test_a_deciding_tally_with_no_recorded_digest_is_refused(tmp_path):
    """§8.7: "every table ledger row records the SHA-256 of its own tally
    file" and "every read rebinds". NB7's finding was that `load_tallies`
    "checks only truthy hashes" and `run_table` "can write
    `tally_sha256=None`" — so an unbound tally read as if it were bound."""
    ledger = tmp_path / "table.jsonl"
    row = {"season": "2019/20", "cutoff_label": "MW6",
           "n_sims": TALLY_N_SIMS, "arms": {}}
    tally = _tally(0)
    _, sha = ew.write_tallies(ledger, row, {"control": tally,
                                            "treatment": tally})
    assert ew.load_tallies(ledger, dict(row, tally_sha256=sha))
    for unbound in (dict(row), dict(row, tally_sha256=None),
                    dict(row, tally_sha256="")):
        with pytest.raises(ew.TableMCImprecise) as exc:
            ew.load_tallies(ledger, unbound)
        assert "records no `tally_sha256`" in str(exc.value)


# --------------------------------------------------------------------------
# v3 — the census the stack can actually price, and the law written against it
#
# `reports/epl_widening_prereg_v3.md` supersedes v2, which its own §8.2 pass 7
# measured as unrunnable: three of its thirty-five mandatory parity cells
# refuse on `epl.particles.ExcludedMassTooLarge` against amendment A1's 0.02
# ceiling. These tests hold the harness to v3's §0.6 census and to the
# residual-list rulings v3 made law.
# --------------------------------------------------------------------------

PREREG_V3 = Path("reports/epl_widening_prereg_v3.md")
PREREG_V2 = Path("reports/epl_widening_prereg_v2.md")


def test_v3_is_the_sole_law_and_v2_is_lineage():
    """§8.1: v3 supersedes v2; v2 "is retained as lineage and decides
    nothing". The freeze guard reads ONE source (§8.6 condition (1)) and it is
    v3 — a guard that read v2's block would bind this run to a document its own
    closing note says cannot be run as written."""
    assert ew.PREREG_PATH.name == "epl_widening_prereg_v3.md"
    assert ew.SCHEMA_ID == "epl-evwiden-3"
    assert ew.PREREG_V2_PATH.name == "epl_widening_prereg_v2.md"
    assert ew.PREREG_V1_PATH.name == "epl_widening_prereg.md"
    # ...and no second source is accepted, in either direction
    for other in (ew.PREREG_V2_PATH, ew.PREREG_V1_PATH, ew.AMENDMENTS_PATH):
        with pytest.raises(ew.EvWidenError):
            ew.harness_freeze_status([other])
        with pytest.raises(ew.EvWidenError):
            ew.harness_freeze_status([ew.PREREG_PATH, other])


def test_the_census_constants_are_v3s_and_not_v2s():
    """§0.6's table, transplanted: 32 cells, 15 treated, 17 untouched, and the
    per-label CELL census v2 never needed because its labels held seven each."""
    assert ew.EXPECTED_TABLE_CELLS == 32
    assert ew.EXPECTED_TABLE_TREATED == 15
    assert ew.EXPECTED_TABLE_UNTOUCHED == 17
    assert ew.EXPECTED_TREATED_BY_LABEL == {
        "MW0": 2, "MW3": 2, "MW6": 7, "MW10": 4, "MW19": 0}
    assert ew.EXPECTED_CELLS_BY_LABEL == {
        "MW0": 5, "MW3": 6, "MW6": 7, "MW10": 7, "MW19": 7}
    assert sum(ew.EXPECTED_CELLS_BY_LABEL.values()) == ew.EXPECTED_TABLE_CELLS
    assert sum(ew.EXPECTED_TREATED_BY_LABEL.values()) == \
        ew.EXPECTED_TABLE_TREATED
    # MW6 is all-treated and is the ONLY all-treated label — §4.1's ground
    all_treated = [lab for lab, n in ew.EXPECTED_TREATED_BY_LABEL.items()
                   if n == ew.EXPECTED_CELLS_BY_LABEL[lab]]
    assert all_treated == ["MW6"]


def test_the_three_unpriceable_cells_are_named_by_key_with_their_masses():
    """§0.6: "the three excluded cells are excluded by measurement and by
    nothing else... named here, named in §3.3, named in the freeze block, and
    named in §10". A caller cannot name, reach or restore them."""
    assert ew.EXCLUDED_CELLS == ("2019/20|MW0", "2020/21|MW0", "2023/24|MW3")
    assert ew.EXCLUDED_CELL_DETAIL["2019/20|MW0"]["fixture"] == \
        "man_city v sheffield_united"
    assert ew.EXCLUDED_CELL_DETAIL["2019/20|MW0"]["excluded_mass"] == 0.0234
    assert ew.EXCLUDED_CELL_DETAIL["2020/21|MW0"]["excluded_mass"] == 0.0216
    assert ew.EXCLUDED_CELL_DETAIL["2023/24|MW3"]["excluded_mass"] == 0.0328
    for detail in ew.EXCLUDED_CELL_DETAIL.values():
        assert detail["refusal_kind"] == "excluded_mass_ceiling"
        assert detail["ceiling"] == 0.02
        assert detail["excluded_mass"] > detail["ceiling"]


@pinned
def test_table_cutoffs_excludes_the_three_and_nothing_else():
    """§3.3: the cells are `SEASONS x COMPARISON_CUTOFFS` minus §0.6's three,
    and "a thirty-third cell, or a thirty-second that is not one of these
    thirty-two, is `MembershipMismatch`"."""
    from epl import baseline, simretro

    matches = baseline.load_matches()
    cells = ew.table_cutoffs(matches)
    assert len(cells) == 32
    keys = {f"{s}|{lab}" for s, lab, _ in cells}
    assert len(keys) == 32
    assert keys.isdisjoint(ew.EXCLUDED_CELLS)
    whole = {f"{s}|{lab}" for s in simretro.SEASONS
             for lab in simretro.COMPARISON_CUTOFFS}
    assert whole - keys == set(ew.EXCLUDED_CELLS)
    by_label = {}
    for _, lab, _ in cells:
        by_label[lab] = by_label.get(lab, 0) + 1
    assert by_label == ew.EXPECTED_CELLS_BY_LABEL


def test_the_per_label_CELL_census_is_pinned_beside_the_treated_one():
    """§3.3: "Both per-label censuses are binding pins". A cell moved between
    labels keeps 32/15 intact and keeps the TREATED census intact — only the
    CELL census sees it, and after §0.6 the labels no longer hold seven each,
    so this pin is load-bearing rather than decorative."""
    good = _census_cells()
    assert ew.assert_table_census(good)["PASS"] is True

    # move one UNTREATED cell from MW19 to MW0: 32/15 and the treated census
    # are all intact, and only EXPECTED_CELLS_BY_LABEL can see it
    moved = [dict(c) for c in good]
    for cell in moved:
        # a season whose MW0 is NOT one of §0.6's exclusions, so the only pin
        # that can see the move is the per-label CELL census
        if (cell["cutoff_label"] == "MW19" and not cell["treated_clubs"]
                and cell["season"] not in ("2019/20", "2020/21")):
            cell["cutoff_label"] = "MW0"
            break
    with pytest.raises(ew.MembershipMismatch) as exc:
        ew.assert_table_census(moved)
    assert "per-label cell census" in str(exc.value)


def test_a_cell_the_census_excluded_may_not_reappear():
    """§10: "a cell §0.6's census measured as unpriceable is added back to the
    oracle" is an invalidation, so the harness refuses it rather than running
    a thirty-third cell."""
    with_excluded = _census_cells() + [
        {"season": "2019/20", "cutoff_label": "MW0", "cutoff": "2019-08-09",
         "clubs": [], "provisional_incumbent": [], "provisional_enlarged": [],
         "treated_clubs": [], "evidence": {}}]
    with pytest.raises(ew.MembershipMismatch) as exc:
        ew.assert_table_census(with_excluded)
    assert "2019/20|MW0" in str(exc.value)


def _census_cells():
    """A synthetic 32-cell census carrying §3.3's own two per-label pins.

    Every value is written literally here, per §7.4."""
    out = []
    for label, n_cells in ew.EXPECTED_CELLS_BY_LABEL.items():
        treated = ew.EXPECTED_TREATED_BY_LABEL[label]
        seasons = [s for s in ("2019/20", "2020/21", "2021/22", "2022/23",
                               "2023/24", "2024/25", "2025/26")
                   if f"{s}|{label}" not in ew.EXCLUDED_CELLS]
        assert len(seasons) == n_cells
        for i, season in enumerate(seasons):
            out.append({"season": season, "cutoff_label": label,
                        "cutoff": "2019-08-09", "clubs": ["a", "b"],
                        "provisional_incumbent": [],
                        "provisional_enlarged": ["a"] if i < treated else [],
                        "treated_clubs": ["a"] if i < treated else [],
                        "evidence": {"a": 0.0, "b": 60.0}})
    return out


def test_the_manifest_is_49_paths_and_its_tallies_are_the_32():
    """§9.3: "an exact list of 49 paths", of which 32 are tallies — "the
    schedule minus the three cells §0.6's census measured as unpriceable"."""
    assert len(ew.MANIFEST_PATHS) == 49
    assert len(set(ew.MANIFEST_PATHS)) == 49
    tallies = [p for p in ew.MANIFEST_PATHS if "/tallies/" in p]
    assert len(tallies) == 32
    for key in ew.EXCLUDED_CELLS:
        season, label = key.split("|")
        name = f"{season.replace('/', '-')}|{label}.npz"
        assert not any(p.endswith(name) for p in tallies), key


# --------------------------------------------------------------------------
# §8.6 — the append-only witness, because a deletable file is not a ratchet
# --------------------------------------------------------------------------

@pytest.fixture()
def _first_fit_paths(tmp_path, monkeypatch):
    """Point BOTH §8.6 artifacts at a tmp_path, together.

    They are one mechanism: pointing one away and leaving the other at its real
    path would test a state the harness never produces."""
    monkeypatch.setattr(ew, "FIRST_FIT_JSON", tmp_path / "first_real_fit.json")
    monkeypatch.setattr(ew, "FIRST_FIT_WITNESS",
                        tmp_path / "first_fit_witness.jsonl")
    return tmp_path


def test_deleting_the_first_fit_record_does_not_reset_the_regime(
        _first_fit_paths):
    """§8.6, B6/NB5. "Absence still returns `None` and restores the pre-fit
    state; enforcement has no independent append-only witness. **Deletion
    therefore still resets the lifecycle.**"

    v3 §8.6: "a witness with lines and no record is a DELETED RECORD — the
    ratchet holds, the state is post-first-fit, and the harness refuses rather
    than quietly reverting to pre-fit."
    """
    assert ew.first_fit_state()["state"] == "pre_first_fit"
    assert ew.witness_lines() == []

    ew.record_first_real_fit(where="a test")
    assert ew.FIRST_FIT_WITNESS.exists()
    assert ew.first_fit_state()["state"] == "post_first_fit"
    assert len(ew.witness_lines()) == 1

    # THE DEFECT, seeded: delete the record and see whether the regime reopens
    ew.FIRST_FIT_JSON.unlink()
    assert ew.first_fit_record() is None            # the file is gone...
    with pytest.raises(ew.FreezeStateUnverified) as exc:
        ew.first_fit_state()                        # ...and the ratchet holds
    assert "DELETED RECORD" in str(exc.value)
    with pytest.raises(ew.FreezeStateUnverified):
        ew.assert_no_hashed_file_moved()


def test_a_record_no_witness_names_is_refused(_first_fit_paths):
    """§8.6: "a record with no witness line naming it is a forged or
    hand-written record and is refused"."""
    ew.FIRST_FIT_JSON.write_text(json.dumps({
        "schema": ew.SCHEMA_ID, "at": "2026-08-29T00:00:00Z",
        "where": "by hand", "prereg": ew.paths.rel(ew.PREREG_PATH),
        "prereg_blob": "0" * 40, "commit": "0" * 40, "harness": {"x": "y"}}))
    with pytest.raises(ew.FreezeStateUnverified) as exc:
        ew.first_fit_state()
    assert "no witness line naming it" in str(exc.value)

    # ...and a witness whose lines name a DIFFERENT fit is the same refusal
    ew.record_first_real_fit(where="a test")        # returns the planted one
    ew.FIRST_FIT_WITNESS.write_text(json.dumps({
        "at": "1999-01-01T00:00:00Z", "where": "elsewhere",
        "chain": "x"}) + "\n")
    with pytest.raises(ew.FreezeStateUnverified):
        ew.first_fit_state()


def test_the_witness_is_append_only_and_its_chain_catches_a_removed_line(
        _first_fit_paths):
    """§8.6: "each appended line carries a CHAIN DIGEST [...] so a line removed
    from the middle breaks every digest after it"."""
    for i in range(3):
        ew.FIRST_FIT_JSON.unlink(missing_ok=True)   # force three appends
        ew.record_first_real_fit(where=f"fit {i}")
    lines = ew.witness_lines()
    assert len(lines) == 3
    # the chain is a real chain: each line's digest covers the one before it
    assert len({ln["chain"] for ln in lines}) == 3

    raw = ew.FIRST_FIT_WITNESS.read_text().splitlines()
    ew.FIRST_FIT_WITNESS.write_text("\n".join([raw[0], raw[2]]) + "\n")
    with pytest.raises(ew.FreezeStateUnverified) as exc:
        ew.witness_lines()
    assert "removed from the middle" in str(exc.value)

    # ...and the harness never opens the witness for truncation
    import inspect
    src = inspect.getsource(ew.record_first_real_fit)
    assert '.open("a")' in src
    assert '.open("w")' not in src and "write_text" not in src.split(
        "FIRST_FIT_WITNESS")[1].split("FIRST_FIT_JSON")[0]


def test_the_witness_line_is_written_before_the_record(_first_fit_paths):
    """§8.6: "a process that dies between the two leaves a witness with no
    record, which reads as post-first-fit — the ratchet holds. The reverse
    order would leave a record no witness names, which reads as forged, and a
    crash is not a forgery." """
    import inspect
    src = inspect.getsource(ew.record_first_real_fit)
    assert src.index("FIRST_FIT_WITNESS.open") < src.index(
        "FIRST_FIT_JSON.write_text")


def test_the_record_is_written_immediately_before_the_sampler(_first_fit_paths):
    """§8.6, IMP-FIRST-FIT-TIMESTAMP. "The old permission-check timestamp was
    moved in `Engine.fit`. But other paths record BEFORE the operation whose
    occurrence they attest: [...] `TableRunner` before protected
    fit/simulation."

    v3 makes the rule uniform: the record is written after the call that
    performs the fit has been entered and immediately before the sampler is
    invoked, at EVERY site.

    The adjudication of 2026-08-29 (F7) adds `run_canary` to the loop — the
    review found the AST test omitting §8.4 step 1, which is the site that
    performs the FIRST four real fits of the whole document — and drops
    `simulate_arm`, which performs no fit and no longer records one."""
    import inspect

    for fn, sampler in ((ew.Engine.fit, "dcfit.fit_epl"),
                        (ew.TableRunner.__call__, "dcfit.fit_epl"),
                        (ew.ParityRunner.__call__, "self._runner("),
                        (ew.run_canary, "runner()")):
        src = inspect.getsource(fn)
        rec = src.index("record_first_real_fit(where=")
        # the sampler CALL that follows the record, not a mention of it in the
        # docstring above
        assert sampler in src[rec:], fn
        between = src[rec:rec + src[rec:].index(sampler)]
        # nothing that could REFUSE stands between the record and the sampler:
        # a timestamp taken before a check that can raise is an attempt
        # timestamp, which is exactly what the review found
        for refusing in ("archive_season_state", "assert_", "raise "):
            assert refusing not in between, (fn, refusing)


def test_the_guard_binds_the_documents_current_bytes_not_only_its_blob():
    """§8.6 condition (1), IMP-POST-FIT-PROSE. "`assert_no_hashed_file_moved`
    binds the preregistration to its committed HEAD blob while current-byte
    checks cover only the two harness files. **An uncommitted post-fit edit to
    v2 is therefore not detected.**"

    v3: "the file's CURRENT bytes must equal that committed blob's [...]
    Committed-blob equality plus current-byte equality is what makes that
    sentence true of a working tree as well as of a commit."
    """
    status = ew.harness_freeze_status()
    assert "prereg_bytes_match_blob" in status
    # the check is real: it compares this file's bytes against its blob
    import inspect
    src = inspect.getsource(ew.harness_freeze_status)
    assert "git_committed_bytes" in src
    assert "PREREG_PATH" in src


# --------------------------------------------------------------------------
# §8.2/§8.4/§8.6 — the residual bypasses, closed
# --------------------------------------------------------------------------

def test_the_launcher_is_refused_pre_freeze_at_every_target(tmp_path):
    """§8.2, IMP-PREFREEZE-SCRIPT. "`write_launch_script` refuses the default
    production target pre-freeze but permits a scratch directory and writes
    inside the repository if that scratch path is outside the narrowly tested
    evwiden directories. **The enumeration remains false.**"

    v3: "`--script` writes the launcher only AFTER the freeze commit [...] so a
    pre-freeze `--script` is refused at EVERY target, not only the default one.
    The refusal is on the freeze state and not on the path."
    """
    assert ew.harness_freeze_status()["frozen"] is False
    for target in (None, tmp_path, tmp_path / "deep" / "nested",
                   ew.paths.REPO_ROOT / "reports", ew.EVWIDEN_DIR):
        with pytest.raises(ew.EvWidenError) as exc:
            ew.write_launch_script(target)
        assert "before §8.3's freeze commit" in str(exc.value), target
    assert not (tmp_path / ew.LAUNCH_NAME).exists()
    assert not (tmp_path / "deep").exists()
    # ...and the CLI action is the same refusal
    assert ew.main(["--script", "--dir", str(tmp_path)]) == 2


def test_the_launcher_takes_no_target_and_no_interpreter():
    """§8.2: "After the freeze, `--script` writes to the preregistered run
    directory and nowhere else. It takes no target that resolves inside the
    repository other than `data/epl/fit/evwiden/launch.sh`, and it takes no
    interpreter, no command prefix and no forwarded keyword arguments."
    """
    import inspect
    params = list(inspect.signature(ew.write_launch_script).parameters)
    assert params == ["directory", "shards"]
    assert ew._no_parameter(ew.write_launch_script, "python", "kwargs")
    assert ew._no_parameter(ew.launch_script, "python", "kwargs")
    assert ew.LAUNCH_PYTHON in ew.launch_script(ew.EVWIDEN_DIR)


def test_the_launcher_emits_step_twos_command_and_its_scratch_target():
    """§8.4, N-RH-FIRST-ACT. "The generated launcher contains only comments for
    that step, then proceeds to later commands. [...] **The sequence remains
    non-executable as written.**"

    v3: step 2 "is a COMMAND, and the launcher runs it", between a
    `need_marker step1_results_canary` command and step 3's.
    """
    text = ew.launch_script(ew.EVWIDEN_DIR)
    commands = [ln.strip() for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    joined = "\n".join(commands)
    assert "--run --limit 1" in joined
    # ...and it names a scratch --dir, which the launcher creates
    step2 = next(c for c in commands if "--limit 1" in c)
    assert "--dir" in step2
    assert str(ew.EVWIDEN_DIR) not in step2.split("--dir")[1].split()[0]
    # the precondition is a COMMAND before it, not a comment naming the marker
    before = commands[:commands.index(step2)]
    assert any(c.startswith("need_marker step1_results_canary")
               for c in before)
    after = commands[commands.index(step2) + 1:]
    assert any(c.startswith("need_marker step2_single_opening") for c in after)


def test_step_two_requires_a_scratch_directory_and_refuses_the_real_one():
    """§8.4: "`--run --limit 1` requires a `--dir` that is NOT the preregistered
    run directory, refuses one that is, and writes its marker to the
    preregistered directory regardless of where its rows went. A step whose only
    legal target the guard refuses is not a step; it is a sentence." """
    assert ew.main(["--run", "--limit", "1", "--dir",
                    str(ew.EVWIDEN_DIR)]) == 2
    # ...and for the step's OWN reason, not because the pre-freeze directory
    # guard happened to catch it first
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ew.main(["--run", "--limit", "1", "--dir", str(ew.EVWIDEN_DIR)])
    assert "SCRATCH directory" in buf.getvalue()
    # ...and the default --dir is the preregistered one, so it is refused too
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ew.main(["--run", "--limit", "1"])
    assert "SCRATCH directory" in buf.getvalue()


def test_the_table_ledger_is_resolved_and_names_nothing(tmp_path):
    """§8.4, P5-B8. "The CLI accepts an arbitrary table ledger [...] After
    seeing the first table outcome, a caller can point to a new ledger and
    execute another table leg; the later marker conflict occurs after the new
    outcome exists."

    v3: "The ledger is therefore resolved from the frozen law and is not a
    parameter of any deciding path [...] And step 5 claims its marker BEFORE it
    simulates."
    """
    import argparse
    import inspect

    # the flag is gone from the CLI's own surface, so argparse itself refuses it
    parser = [n for n in inspect.getsource(ew.main).splitlines()
              if "add_argument" in n]
    assert not any("table-ledger" in n or "table_ledger" in n for n in parser)
    with pytest.raises(SystemExit):
        ew.main(["--table-ledger", str(tmp_path / "x.jsonl"), "--verify"])
    # ...and the ledger is derived from --dir and from nothing a caller names
    body = inspect.getsource(ew.main)
    assert "table_ledger = (TABLE_LEDGER if directory == EVWIDEN_DIR" in body

    # step 5 CLAIMS its write-once marker BEFORE the expensive run, so a second
    # attempt dies at the claim rather than after a second outcome exists
    branch = body[body.index("if args.table:"):]
    assert branch.index("claim_sequence_step") < branch.index("run_table("), \
        "the marker is claimed first"
    assert ew._no_parameter(ew.claim_sequence_step, "produced", "complete")


def test_merge_and_the_table_legs_enforce_the_sequence_themselves(tmp_path,
                                                                  monkeypatch):
    """§8.6, NB6. "`run_table` itself has no sequence requirement; `merge` is
    callable without the CLI sequence."

    v3: "`merge`, `run_table` and `run_parity_oracle` require the sequence
    themselves. Each calls §8.4's marker check for its own step on every
    invocation — not only when reached through `main` — so a direct API call is
    exactly as ordered as a command line."
    """
    for fn, index in ((ew.merge, 3), (ew.run_table, 4),
                      (ew.run_parity_oracle, 4)):
        calls = ew._calls_made(fn)
        assert "require_sequence" in calls, fn
        # ...and it is THIS function's own step, named through SEQUENCE_STEPS
        # so the two cannot drift
        assert f"require_sequence(SEQUENCE_STEPS[{index}])" in \
            inspect_source(fn), (fn, index)


def inspect_source(fn):
    import inspect
    return inspect.getsource(fn)


def test_a_marker_without_complete_unlocks_nothing(tmp_path, monkeypatch):
    """§8.6, NB6. "Marker validation does not require `complete` [...] Missing
    `complete` is treated as TRUE on read."

    v3: "It must carry `complete: true` — a missing `complete` is FALSE, never
    true-by-absence."
    """
    monkeypatch.setattr(ew, "SEQUENCE_DIR", tmp_path / "sequence")
    monkeypatch.setattr(ew, "_frozen_now", lambda: True)
    monkeypatch.setattr(ew, "harness_freeze_status",
                        lambda *a, **k: {"frozen": True})
    ew.write_sequence_marker("step1_results_canary", produced={"n": 1})
    assert ew.require_sequence("step2_single_opening")["PASS"] is True

    marker = ew.sequence_marker_path("step1_results_canary")
    body = json.loads(marker.read_text())
    body.pop("complete")
    marker.write_text(json.dumps(body))
    with pytest.raises(ew.SequenceViolation) as exc:
        ew.require_sequence("step2_single_opening")
    assert "complete" in str(exc.value)


def test_score_table_derives_its_deciding_evidence_and_cannot_be_handed_it():
    """§8.6, NB7. "`score_table(tallies=..., mc=...)` still accepts
    caller-supplied deciding evidence. The guard is keyed to `ledger_path`, so
    supplying tallies while pointing at a scratch path avoids the production
    refusal."

    v3: "There is no `tallies=` and no `mc=` on any deciding path, at any
    target. §5's estimator and §5.4's unanimity rule are computed, not
    accepted."
    """
    assert ew._no_parameter(ew.score_table, "tallies", "mc")
    assert ew._no_parameter(ew.table_gate, "mc", "unanimity", "tallies")


def test_the_guard_does_not_refuse_every_artifact_under_the_shared_fit_dir(
        tmp_path):
    """§8.6, P5-I2. "`PREREGISTERED_DIRS` includes all `paths.FIT_DIR`. Any
    unrelated scratch audit below that shared directory is refused, even though
    the document closes the evwiden artifacts, not every fit artifact."

    v3: "`paths.FIT_DIR` itself is not a preregistered directory and a target
    merely INSIDE it is not refused for that reason alone."
    """
    assert ew.paths.FIT_DIR not in ew.PREREGISTERED_DIRS
    # an unrelated neighbour under the shared directory is permitted...
    ew.assert_seam_allowed("an unrelated audit", target=ew.paths.FIT_DIR
                           / "some_other_experiment" / "rows.jsonl")
    # ...and this experiment's own artifacts, named individually, are not
    for closed in (ew.EVWIDEN_DIR / "x", ew.TABLE_DIR / "x",
                   ew.SEQUENCE_DIR / "x", ew.EVIDENCE_DIR / "x",
                   ew.EVWIDEN_JSON, ew.FEASIBILITY_RECORD,
                   ew.FIRST_FIT_JSON, ew.FIRST_FIT_WITNESS):
        with pytest.raises(ew.EvWidenError):
            ew.assert_seam_allowed("this experiment's own", target=closed)
    # ...and the enumeration is COMPLETE: every path this experiment writes is
    # covered by it. That is what replaces the wildcard — an exact list a test
    # reads back, so a new evwiden artifact outside it fails here rather than
    # being caught by a pattern nobody wrote down.
    for written in ew.WRITES:
        assert ew._is_preregistered_target(written), written
    for named in ew.preregistered_files():
        assert ew._is_preregistered_target(named), named


def test_the_read_only_store_closes_its_check_then_construct_window(tmp_path,
                                                                    monkeypatch):
    """§8.2, MIN-READ-ONLY-STORE-TOCTOU. "`read_only_store` checks that
    `results.parquet` exists and then constructs `BitemporalStore`. The
    constructor CREATES its root directory, and existence can change between
    check and construction."

    v3: the accessor "records the root's existence, the parquet's existence, its
    byte size and its mtime BEFORE constructing anything [...] and re-verifies
    the same four afterwards".
    """
    root = tmp_path / "store"
    root.mkdir()
    (root / ew.STORE_TABLE_PARQUET).write_bytes(b"x")

    class _Vanishing:
        """A store whose root is removed at construction — the TOCTOU window."""
        def __init__(self, r):
            import shutil
            shutil.rmtree(r)
            Path(r).mkdir(parents=True)      # what BitemporalStore.__init__ does

    import wcmodel.data.store as store_mod
    monkeypatch.setattr(store_mod, "BitemporalStore", _Vanishing)
    monkeypatch.setattr(ew, "PREREGISTERED_DIRS", ())    # a scratch root
    with pytest.raises(ew.StoreNotBuilt) as exc:
        ew.read_only_store(root=root)
    assert "CREATED OR MOVED" in str(exc.value)


def test_the_read_only_store_removes_the_tree_it_was_made_to_create(
        tmp_path, monkeypatch):
    """The adjudication of 2026-08-29, F11 (MIN-READ-ONLY-STORE-TOCTOU).
    "Re-check after construction; REMOVE a directory the constructor created on
    the refusal path; test asserts removal."

    Re-checking makes the write VISIBLE; it does not undo it. §8.2's clause is
    that an absent store stays absent — "it never builds, never writes, never
    unlinks" — and a refusal that leaves `paths.STORE_DIR` standing where the
    accessor found nothing has built one and then complained about it.
    """
    root = tmp_path / "absent_store"          # the store is NOT on disk

    class _Creating:
        """`BitemporalStore.__init__` as it really is: it creates its root."""
        def __init__(self, r):
            Path(r).mkdir(parents=True, exist_ok=True)

    import wcmodel.data.store as store_mod
    monkeypatch.setattr(store_mod, "BitemporalStore", _Creating)
    monkeypatch.setattr(ew, "PREREGISTERED_DIRS", ())    # a scratch root

    # the parquet is absent, so the accessor refuses before constructing —
    # and nothing was created
    with pytest.raises(ew.StoreNotBuilt):
        ew.read_only_store(root=root)
    assert not root.exists()

    # ...and when the parquet vanishes between the check and the construction,
    # the constructor's directory is REMOVED on the way out
    parquet = root / ew.STORE_TABLE_PARQUET
    root.mkdir()
    parquet.write_bytes(b"x")

    class _Eating(_Creating):
        def __init__(self, r):
            parquet.unlink()
            import shutil
            shutil.rmtree(r)
            super().__init__(r)

    monkeypatch.setattr(store_mod, "BitemporalStore", _Eating)
    with pytest.raises(ew.StoreNotBuilt) as exc:
        ew.read_only_store(root=root)
    assert "CREATED OR MOVED" in str(exc.value)
    assert "REMOVED on the way out" in str(exc.value)
    assert not root.exists(), "the refusal left the tree the constructor built"


# ==========================================================================
# §8.5 — the report may not be its own witness
#
# v3 §8.5: "§8.5's eighteen scenarios are COMMITTED PYTEST TESTS, one per row,
# with stable test ids. They are executed by a pytest invocation that emits a
# machine-readable JSON report of that run. `--conformance` and `--freeze-block`
# READ that artifact and cross-check it three ways: the test ids are exactly the
# eighteen; every one of the eighteen outcomes is `passed`; the reported count
# is eighteen."
#
# The eighteen tests are below. Each executes ONE row's scenario through
# `ew.conformance_row`, and the session fixture writes the artifact from what
# they actually did. `_CONFORMANCE_OUTCOMES` starts each row at "failed" and is
# only moved to "passed" after the assertion holds, so a row that raises leaves
# the failure on the record.
# ==========================================================================

_CONFORMANCE_OUTCOMES: dict[str, str] = {}


@pytest.fixture(scope="session", autouse=True)
def _the_conformance_artifact():
    """Write §8.5's artifact at SESSION teardown, from what the runs did.

    Session teardown is outside every function-scoped fixture, which is why the
    isolation fixture does not see this write — and why the write happens once,
    after all eighteen rows have had their chance to run.
    """
    yield
    if _CONFORMANCE_OUTCOMES:
        ew.write_conformance_artifact(_CONFORMANCE_OUTCOMES)


def _conformance(row_id: str) -> None:
    _CONFORMANCE_OUTCOMES[row_id] = "failed"
    row = ew.conformance_row(row_id)
    assert row["ok"], row
    _CONFORMANCE_OUTCOMES[row_id] = "passed"


def test_conformance_L1(): _conformance("L1")
def test_conformance_L2(): _conformance("L2")
def test_conformance_L3(): _conformance("L3")
def test_conformance_L4(): _conformance("L4")
def test_conformance_L5(): _conformance("L5")
def test_conformance_L6(): _conformance("L6")
def test_conformance_L7(): _conformance("L7")
def test_conformance_L8(): _conformance("L8")
def test_conformance_L9(): _conformance("L9")
def test_conformance_L10(): _conformance("L10")
def test_conformance_L11(): _conformance("L11")
def test_conformance_L12(): _conformance("L12")
def test_conformance_L13(): _conformance("L13")
def test_conformance_L14(): _conformance("L14")
def test_conformance_L15(): _conformance("L15")
def test_conformance_L16(): _conformance("L16")
def test_conformance_L17(): _conformance("L17")
def test_conformance_L18(): _conformance("L18")


def test_the_freeze_reads_an_artifact_it_did_not_write(tmp_path, monkeypatch):
    """§8.5, NB8 and the L1-L18 independence problem. "`freeze_block` consumes
    `implementation_report` and BELIEVES EACH ROW'S OWN `ok` FIELD [...] The
    report is still capable of certifying itself."

    v3: the report is a READING of a pytest run. A row is green iff its own test
    id is present and passed in the artifact, and the harness "may not mark a row
    green from anything it computed itself"."""
    monkeypatch.setattr(ew, "CONFORMANCE_ARTIFACT", tmp_path / "conf.json")
    assert ew.CONFORMANCE_ROWS == tuple(f"L{i}" for i in range(1, 19))

    # (a) absent
    with pytest.raises(ew.EvWidenError) as exc:
        ew.assert_conformance_artifact()
    assert "no pytest artifact" in str(exc.value)

    # (b) a SUBSET, all green — the acceptance v2's guard made
    ew.write_conformance_artifact({r: "passed" for r in ew.CONFORMANCE_ROWS[:9]})
    with pytest.raises(ew.EvWidenError) as exc:
        ew.assert_conformance_artifact()
    assert "exactly" in str(exc.value)

    # (c) all eighteen ids, one of them not passed — skip, error and xfail are
    #     each a scenario that did not run
    for outcome in ("failed", "skipped", "error", "xfailed"):
        ew.write_conformance_artifact(
            {**{r: "passed" for r in ew.CONFORMANCE_ROWS}, "L7": outcome})
        with pytest.raises(ew.EvWidenError) as exc:
            ew.assert_conformance_artifact()
        assert "L7" in str(exc.value), outcome

    # (d) a nineteenth id
    ew.write_conformance_artifact(
        {**{r: "passed" for r in ew.CONFORMANCE_ROWS}, "L19": "passed"})
    with pytest.raises(ew.EvWidenError):
        ew.assert_conformance_artifact()

    # (e) exactly the eighteen, all passed
    ew.write_conformance_artifact({r: "passed" for r in ew.CONFORMANCE_ROWS})
    status = ew.assert_conformance_artifact()
    assert status["count"] == 18 and status["ok"] is True
    assert status["test_ids"] == [f"epl/tests/test_evwiden.py::test_conformance_{r}"
                                  for r in ew.CONFORMANCE_ROWS]
    assert len(status["sha256"]) == 64


def test_the_freeze_block_records_which_run_certified_it(tmp_path, monkeypatch):
    """§8.5: "Its path, its SHA-256, its test-id list and its pass count go
    into the freeze block, so the committed block records WHICH RUN certified
    the freeze." """
    monkeypatch.setattr(ew, "CONFORMANCE_ARTIFACT", tmp_path / "conf.json")
    with pytest.raises(ew.EvWidenError):
        ew.freeze_block()                    # no artifact, no block
    ew.write_conformance_artifact({r: "passed" for r in ew.CONFORMANCE_ROWS})
    block = ew.freeze_block()
    status = ew.conformance_artifact_status()
    assert status["sha256"] in block
    assert "18" in block
    for row_id in ew.CONFORMANCE_ROWS:
        assert f"test_conformance_{row_id}" in block, row_id


@pinned
def test_the_committed_block_must_carry_exactly_the_eighteen_rows(
        monkeypatch, tmp_path, unrun_feasibility):
    """§8.6 condition (5). "The committed-block guard accepts any nonempty
    all-green SUBSET rather than exactly L1-L18."

    v3: "A nonempty all-green SUBSET fails this condition" — at both ends, and
    the redundancy is deliberate: one guards what is rendered, the other guards
    what a later fit reads back out of the commit."""
    block = ew.freeze_block()
    monkeypatch.setattr(ew, "git_committed_bytes",
                        _as_if_committed(block, monkeypatch=monkeypatch))
    assert ew.harness_freeze_status()["frozen"] is True

    # drop three rows from the COMMITTED block and keep the rest green
    trimmed = "\n".join(line for line in block.splitlines()
                        if not any(f"| {r} |" in line for r in ("L16", "L17",
                                                                "L18")))
    monkeypatch.setattr(ew, "git_committed_bytes",
                        _as_if_committed(trimmed, monkeypatch=monkeypatch))
    status = ew.harness_freeze_status()
    assert status["frozen"] is False
    assert "exactly" in status["why"]


def test_the_artifact_names_the_harness_it_ran_against(tmp_path, monkeypatch):
    """§8.5: "an artifact from a different harness fails §8.6's harness-hash
    condition alongside it" — which is true of a COMMITTED block, but a block
    rendered NOW from a stale artifact would carry current harness digests
    beside a run of older bytes, and condition (2) compares the block to the
    tree rather than the artifact to either. The artifact carries its own."""
    monkeypatch.setattr(ew, "CONFORMANCE_ARTIFACT", tmp_path / "conf.json")
    ew.write_conformance_artifact({r: "passed" for r in ew.CONFORMANCE_ROWS})
    assert ew.conformance_artifact_status()["ok"] is True

    body = json.loads(ew.CONFORMANCE_ARTIFACT.read_text())
    body["harness"][ew.HARNESS_FILES[0]] = "0" * 64
    ew.CONFORMANCE_ARTIFACT.write_text(json.dumps(body))
    status = ew.conformance_artifact_status()
    assert status["ok"] is False
    assert "different harness bytes" in status["why"]
    with pytest.raises(ew.EvWidenError):
        ew.assert_conformance_artifact()


def test_the_rendered_block_is_a_paste_and_not_a_transcription(unrun_feasibility,
                                                               capsys):
    """§8.3 step 2: the commit APPENDS the rendered block. Anything the render
    prints alongside it lands in the document, so §8.5's CLI probes — each of
    which is `main` correctly writing a `STOP:` line — must not reach stdout."""
    capsys.readouterr()
    block = ew.freeze_block()
    out = capsys.readouterr().out
    assert "STOP:" not in out, out[:400]
    assert "STOP:" not in block
    # ...and §8.3's membership list is complete: both per-label censuses and
    # the three keys §0.6 measured as unpriceable
    assert "the per-label treated census" in block
    assert "the per-label CELL census" in block
    assert "measured as UNPRICEABLE" in block
    # ...each key with its `|` ESCAPED, because an unescaped pipe inside a
    # markdown cell splits the row and §8.6 condition (3) would then read a
    # membership table whose columns had shifted
    escaped = "\\|"          # a `|` inside a markdown cell splits the row
    for key in ew.EXCLUDED_CELLS:
        assert key.replace("|", escaped) in block, key
        assert f"| {key} |" not in block, key
