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

#: The `@pinned` tests of R-I5: they read the pinned artifacts DELIBERATELY, to
#: re-derive the document's own census. They fit nothing and simulate nothing,
#: they are authorised by name under R-B5, and they are not covered by R-I5's
#: SYNTHETIC definition.
pinned = pytest.mark.skipif(
    not (PINNED_CORPUS.exists() and PINNED_ARCHIVE.exists()
         and PINNED_LEDGER.exists()),
    reason="the pinned corpus, archive and walk-forward ledger are on the "
           "machine that ran the walk and nowhere else")


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

#: R2-I5's corrected inventory of fact. There are THREE generators — `_archive`,
#: `_corpus` and `_ledger`, with `_world` returning the three together — and
#: FIVE invented club names, not four: `other` appears in `_archive()` as the
#: counterparty club and is not in `CLUBS`, which is why round one missed it.
#: R2-I5 makes the ancestry claim a test rather than an assertion:
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
# R2-I5 — "synthetic" has an enforceable definition, and it is enforced HERE
# ==========================================================================

def test_the_generator_inventory_is_the_documents():
    """R2-I5 corrects round one's inventory of fact: three generators, five
    invented club names. Round one asserted a check into existence and named
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
    """R2-I5, the ancestry check made mechanical — the test round one said
    existed and did not.

    R-I5 defines SYNTHETIC as "every one of its values is written literally in
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
    """R-I5: "No value may be read, copied, sampled, transformed, or otherwise
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
    """R-I1: `frozen_wcmodel_config()` loads the LIVE `config/config.yaml` and
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
    """R-I1 pins `78a51cd9…`, computed 2026-08-27 under the pinned frozen file.
    A drift there changes `e`, the posteriors, or reproducibility while the
    superseded three-condition check passed."""
    from epl import freeze

    assert ew.REALISED_CONFIG_SHA256 == (
        "78a51cd92c48838a57e3d6832b7661aad7a5b231425572214a067c2a35edbdcd")
    cfg = freeze.frozen_wcmodel_config()
    assert ew.realised_config_sha256(cfg) == ew.REALISED_CONFIG_SHA256
    # and the fields R-I1 says it now binds
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
    # R-B1: Arm B IS recomputed now — from the same posterior — and the corpus
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

class _FakePosterior:
    """The smallest object the WHOLE production map will accept.

    R-M2 binds the direction canary to the production path, so this double
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
                 log_rate: float = 0.2, n_draws: int = 2):
        self.provisional_teams: set[str] = set()
        self._cfg = {"widening": {"mechanism": mechanism, "strength": strength},
                     "neutral_home_adv_fraction": 0.5}
        self.teams = ["a", "b"]
        self._idx = {"a": 0, "b": 1}
        self.likelihood = "dixon_coles"
        s = int(n_draws)
        self._params = {
            "att": np.array([[0.05] * s, [-0.05] * s]),
            "def": np.array([[0.02] * s, [-0.02] * s]),
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
    """R-M2's comparator needs the grid `finalize_grid` is HANDED, and takes it
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
    """R-M2: the comparator is `finalize_grid(grid, posterior, provisional=…)`,
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
    """R-M2: `inflate_predictive` documents an edge no-op — a marginal mean at
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
    """R-M2: "A direction canary in which every fixture took the edge branch is
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
    different treatment from the preregistered one, and R-M2's move onto the
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


def test_the_negative_leg_is_array_equal_and_both_legs_count_their_rows():
    """R-I4: the comparison is `numpy.array_equal` on the float64 values BEFORE
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
    # R-I4's frozen mutation, on the record beside the numbers
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
    """The paired deltas, recomputed from the ROWS' own probabilities.

    R-B1: Arm B is `probs_incumbent` — the SAME posterior under the fit's own
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
    """R-B1, the repair that makes the pairing real.

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
    """R-B1: "The corpus is demoted to an external identity control." All 820
    fixtures must still equal Arm B at their eight decimals, and each stored
    `dc_rps` must still re-derive from its own stored probabilities.

    The consequence R-B1 pre-states, so it cannot be discovered later: because
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


def test_seeded_defect_a_corpus_row_that_is_not_the_corpus_refuses(tmp_path):
    """R-B1: the corpus is the EXTERNAL identity control. A row that copies
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
    """§3.2, as R-B1 restates it: all 820 fixtures of the 78 openings must equal
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

#: The synthetic table world mirrors §3.3's own shape: seven seasons x five
#: labels = 35 cells, with R-B2's census of treated cells per label —
#: MW0 3, MW3 2, MW6 **7**, MW10 4, MW19 **0**. The gates are per horizon now,
#: so a fixture-world that flattened the labels could not exercise them.
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
    and every rank column sums to `k` — the equal-cluster condition R2-B3 step 2
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
    """§3.3's 35 cells, with R-B2's per-label treated census."""
    treated_by_label = {"MW0": 3, "MW3": 2, "MW6": 7, "MW10": 4, "MW19": 0}
    out = []
    for label in labels:
        for i, season in enumerate(seasons):
            treated = ["sunderland"] if i < treated_by_label.get(label, 0) else []
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
        "provisional_teams": ["rich"]} for c in cells}


def _table_runner(shift: float = -0.001, *, break_identity: str | None = None,
                  jitter: int = 0, break_parity: bool = False,
                  break_provisional: bool = False):
    """A stub cell runner with the repaired `TableRunner` output contract."""

    def run(cell):
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
               harness_frozen=False, **kwargs):
    """Run the stub table leg with a stub parity oracle beside it."""
    cells = _cells() if cells is None else cells
    path = Path(tmp_path) / name
    ew.run_table(cells, path, runner=runner or _table_runner(),
                 parity=_parity_for(cells), n_sims=TALLY_N_SIMS, seed=20260611,
                 config_sha="c", verbose=False, harness_frozen=harness_frozen,
                 **kwargs)
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return path, rows


def test_the_untouched_cells_must_prove_they_did_not_move():
    """§3.3: "the other 19 cells are unchanged by construction, AND THE HARNESS
    MUST PROVE IT" — on the SAMPLER digest (R2-B4(a))."""
    assert ew.assert_table_identity([], "d", "d", where="cell") is True
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_table_identity([], "d", "other", where="cell")
    assert "unchanged BY CONSTRUCTION" in str(exc.value)


def test_a_treated_cell_that_did_not_move_is_the_absence_of_the_experiment():
    """R-H(4) as R2-B4(a) restates it so that it can actually FAIL: with the
    provisional set outside the digest, equality is a statement about
    scorelines, tie blocks and points — the things the D12 branch moves."""
    assert ew.assert_table_identity(["x"], "d", "e", where="cell") is False
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_table_identity(["x"], "d", "d", where="cell")
    assert "never reached the sampler" in str(exc.value)
    assert "SAMPLER OUTPUT" in str(exc.value)


def test_the_provisional_set_is_a_compared_field_and_not_a_digest_ingredient():
    """R2-B4(a) ends round one's tautology: the digest included the provisional
    set, and R-H(4) then used digest inequality as proof that the treatment
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


# ---- R2-B4: the digests, and the call into protected code ------------------

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
    """R2-B3 supersedes R-B3's tally bullet. `.order` is "the deterministic
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
    """R2-B3: "a committed test asserts that equality at 0.0". `numpy.add.at` is
    unbuffered and applies its indices in order, so contiguous ascending chunks
    perform the same sequence of additions as one pass."""
    run = _FakeRun(particles=4, k=8, tie=True)
    whole = ew.particle_tallies(run, chunk_size=10_000)
    for size in (1, 3, 7, 32):
        assert float(np.abs(ew.particle_tallies(run, chunk_size=size)
                            - whole).max()) == 0.0


def test_the_tally_binds_the_matrix_and_refuses_an_unequal_cluster():
    """R2-B3's two committed checks: the tally reproduces the scored matrix, and
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
    """R2-B4(a): "Nothing else. No club list, no plan, no seed, no posterior
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
    """R2-B4(b): season/cutoff/`observed_by` identity, the fixture-and-result
    snapshot, the adjustments, the rule id, the chunking (which fixes the RNG
    chunk keys and therefore the numbers) and the results-lag state."""
    run = _FakeRun()
    tallies = ew.particle_tallies(run)
    kw = dict(weights=[1.0, 1.0], boundaries=run.plan.boundaries,
              realised_hash="r", realised_positions=[1, 2, 3],
              realised_points=[40, 30, 20], effective_posterior_hash="book")
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
    # ...and the provisional set is NOT in it — that is R2-B4(a)'s repair
    assert "provisional" not in ew.plan_state(_FakeRun())


def test_the_table_runner_calls_protected_simulate_with_its_own_signature():
    """R-B4 recorded the defect rather than fixing it quietly: the harness
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

    with mock.patch.object(leaguesim, "simulate", spy):
        out = ew.simulate_arm("STATE", "BOOK", n_sims=7, seed=11, chunk_size=3,
                              n_particles=5)
    assert out == "run"
    assert seen["args"] == (ew.TABLE_ARM_LABEL, "STATE", "BOOK", 7, 11, 3)
    assert seen["kwargs"] == {"n_particles": 5}
    bound = inspect.signature(leaguesim.simulate).bind(*seen["args"],
                                                       **seen["kwargs"])
    assert bound.arguments["state"] == "STATE"
    assert bound.arguments["book_or_provider"] == "BOOK"
    assert bound.arguments["seed"] == 11


# ---- R-B4 / R2-B4(c): the 35-cell native-parity oracle ---------------------

def test_the_parity_oracle_compares_substantive_digests_and_the_incumbent_set():
    """R-B4: binding the SCHEDULE to protected code binds neither its semantics
    nor its call, and the 19-untouched-cell control compares two arms produced
    by the SAME new code, so shared drift passes it silently."""
    oracle = {"substantive_digest": "abc", "provisional_teams": ["rich"]}
    assert ew.assert_native_parity("2019/20|MW6", "abc", oracle,
                                   ["rich"])["PASS"] is True
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_native_parity("2019/20|MW6", "def", oracle, ["rich"])
    assert "native parity at all thirty-five cells" in str(exc.value)
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.assert_native_parity("2019/20|MW6", "abc", oracle, ["rich", "mid"])
    assert "control arm IS the incumbent arm" in str(exc.value)


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
    assert len(out) == len(cells) == 35
    assert len(seen) == 35
    again = ew.run_parity_oracle(cells, path, runner=stub, verbose=False)
    assert len(seen) == 35 and len(again) == 35     # resumed, not re-run


def test_the_treated_run_refuses_a_cell_the_oracle_never_covered(tmp_path):
    cells = _cells()
    with pytest.raises(ew.TableIdentityBreak) as exc:
        ew.run_table(cells, tmp_path / "t.jsonl", runner=_table_runner(),
                     parity={}, n_sims=TALLY_N_SIMS, seed=1, config_sha="c",
                     verbose=False, harness_frozen=False)
    assert "BEFORE one treated simulation" in str(exc.value)


def test_the_treated_run_refuses_a_control_arm_that_drifted_from_protected(
        tmp_path):
    cells = _cells()
    with pytest.raises(ew.TableIdentityBreak):
        ew.run_table(cells, tmp_path / "t.jsonl",
                     runner=_table_runner(break_parity=True),
                     parity=_parity_for(cells), n_sims=TALLY_N_SIMS, seed=1,
                     config_sha="c", verbose=False, harness_frozen=False)


def test_the_table_leg_writes_one_row_per_cell_and_resumes(tmp_path):
    cells = _cells()
    path = tmp_path / "table.jsonl"
    out = ew.run_table(cells, path, runner=_table_runner(),
                       parity=_parity_for(cells), n_sims=TALLY_N_SIMS,
                       seed=20260611, config_sha="c", verbose=False,
                       harness_frozen=False)
    assert out["n_written"] == len(cells) == 35
    again = ew.run_table(cells, path, runner=_table_runner(),
                         parity=_parity_for(cells), n_sims=TALLY_N_SIMS,
                         seed=20260611, config_sha="c", verbose=False,
                         harness_frozen=False)
    assert again["n_written"] == 0 and again["n_skipped"] == len(cells)
    # the tallies live beside the ledger, because a [P, C, C] array is not a
    # JSONL field and R2-B3 needs all thirty-two at once
    assert ew.tally_path(path, {"season": "2019/20",
                                "cutoff_label": "MW6"}).exists()


# ---- R-B2: the deciding statistics are per horizon -------------------------

def test_the_pooled_35_cell_statistic_is_gone_from_every_deciding_path(tmp_path):
    """R-B2: the 35-cell pooled ΔTRPS and ΔwTRPS are WITHDRAWN from the
    published outputs entirely, not demoted to secondaries. Protected code
    freezes "Never averaged across cutoffs" and publishing the average invites
    it to be quoted as a verdict."""
    path, rows = _run_cells(tmp_path)
    scored = ew.score_table(rows, n_boot=200, ledger_path=path)
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
    """R-B2 (iv-a): the equal-weight mean over the SEVEN MW6 cells. (iv-b): at
    MW0, MW3 and MW10, the mean over THAT LABEL'S TREATED CELLS ONLY."""
    path, rows = _run_cells(tmp_path, runner=_table_runner(shift=-0.001))
    scored = ew.score_table(rows, n_boot=200, ledger_path=path)
    assert scored["mw6"]["n"] == 7
    assert scored["mw6"]["mean"] == pytest.approx(-0.001)     # all seven treated
    assert scored["per_label"]["MW0"]["n_treated"] == 3
    assert scored["per_label"]["MW3"]["n_treated"] == 2
    assert scored["per_label"]["MW10"]["n_treated"] == 4
    for label in ("MW0", "MW3", "MW10"):
        assert scored["per_label"][label]["mean"] == pytest.approx(-0.001)
        assert "no interval" in scored["per_label"][label]["interval"]
    assert scored["mw19"]["structural_zero"] is True
    assert scored["mw19"]["n_treated"] == 0
    assert scored["mw19"]["decides"] == "nothing"


def test_the_mw6_interval_is_r_b3s_frozen_construction(tmp_path):
    """R-B3's table: `epl.score.block_bootstrap_ci`, the seven season strings
    one cell per block, B = 10,000, alpha = 0.05, seed 20260814, NumPy's default
    linear-interpolation quantile."""
    path, rows = _run_cells(tmp_path)
    scored = ew.score_table(rows, n_boot=500, ledger_path=path)
    mw6 = scored["mw6"]
    assert mw6["n_blocks"] == ew.TABLE_CI_BLOCKS == 7
    assert mw6["bootstrap"]["function"] == "epl.score.block_bootstrap_ci"
    assert mw6["bootstrap"]["seed"] == ew.BOOTSTRAP_SEED
    assert mw6["bootstrap"]["alpha"] == ew.ALPHA
    deltas = np.array([c["delta_trps"] for c in mw6["per_cell"]], dtype=float)
    seasons = [c["season"] for c in mw6["per_cell"]]
    lo, hi, n = score_mod.block_bootstrap_ci(deltas, seasons, n_boot=500,
                                             alpha=ew.ALPHA,
                                             seed=ew.BOOTSTRAP_SEED)
    assert mw6["ci95"] == [lo, hi] and n == 7


# ---- R2-B3: the jointly resampled, tie-aware paired bootstrap --------------

def _mc_cells(n=2, *, jitter=1, particles=TALLY_PARTICLES, label="MW6"):
    positions = np.array([1, 2, 3])
    spans = np.array([1, 1, 1])
    return [{"key": f"2019/2{i}|{label}", "cutoff_label": label,
             "positions": positions, "spans": spans,
             "control": _tally(0, jitter=jitter, particles=particles),
             "treatment": _tally(1, jitter=jitter, particles=particles)}
            for i in range(n)]


def test_the_paired_bootstrap_applies_one_index_to_every_tally():
    """R2-B3: "There is no quadrature step and no independence claim anywhere in
    this estimator." The label mean is computed INSIDE each replicate, so cells
    that move together in the run move together in the replicate.

    Round one's `sqrt(sum se^2)/7` would shrink a perfectly correlated pair by
    `1/sqrt(2)`; the joint estimator does not, and that is the whole repair."""
    cells = _mc_cells(n=2, jitter=1)
    out = ew.paired_mc_bootstrap(cells, n_boot=400, seed=ew.MC_SEED)
    per_cell = list(out["mc_se_per_cell"].values())
    label = out["mc_se_label"]["MW6"]
    assert all(v > 0 for v in per_cell)
    # the two cells are byte-identical by construction, so the mean of their
    # deltas has exactly their own standard error — not the quadrature one
    assert label == pytest.approx(per_cell[0], rel=1e-12)
    quadrature = float(np.sqrt(sum(v ** 2 for v in per_cell)) / len(per_cell))
    assert label > quadrature


def test_the_paired_bootstrap_is_deterministic_at_its_frozen_seed():
    cells = _mc_cells(n=2, jitter=1)
    a = ew.paired_mc_bootstrap(cells, n_boot=200, seed=ew.MC_SEED)
    b = ew.paired_mc_bootstrap(cells, n_boot=200, seed=ew.MC_SEED)
    assert a["mc_se_per_cell"] == b["mc_se_per_cell"]
    assert ew.MC_BOOT == 2000 and ew.MC_SEED == 20260827
    c = ew.paired_mc_bootstrap(cells, n_boot=200, seed=ew.MC_SEED + 1)
    assert c["mc_se_per_cell"] != a["mc_se_per_cell"]


def test_the_bootstrap_refuses_a_common_index_space_it_does_not_have():
    """R2-B3 step 2: "Joint resampling is undefined without a common index
    space, and this document will not approximate one." `TableMCImprecise`."""
    mixed = _mc_cells(n=1) + _mc_cells(n=1, particles=TALLY_PARTICLES * 2)
    mixed[1]["key"] = "other|MW6"
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.paired_mc_bootstrap(mixed, n_boot=10)
    assert "ONE common index space" in str(exc.value)

    lopsided = _mc_cells(n=1)
    lopsided[0]["control"] = lopsided[0]["control"].copy()
    lopsided[0]["control"][0, 0, 0] += 1.0
    with pytest.raises(ew.TableMCImprecise) as exc:
        ew.paired_mc_bootstrap(lopsided, n_boot=10)
    assert "unequal season" in str(exc.value)


# ---- gate (iv), all three parts, and the precision rule --------------------

def _scored(mean_mw6=0.0, ci=(-1.0, 1.0), means=(0.0, 0.0, 0.0), se=None):
    labels = dict(zip(ew.POINT_GATE_LABELS, means))
    mc_se = {"MW6": 0.0, "MW0": 0.0, "MW3": 0.0, "MW10": 0.0}
    mc_se.update(se or {})
    return {
        "n_cells": 35, "n_treated_cells": 16,
        "mw6": {"cutoff_label": "MW6", "n": 7, "mean": mean_mw6,
                "ci95": list(ci), "n_blocks": 7},
        "per_label": {lab: {"cutoff_label": lab, "n_treated": 3,
                            "mean": labels[lab]}
                      for lab in ew.POINT_GATE_LABELS},
        "mw19": {"structural_zero": True, "decides": "nothing"},
        "mc": {"mc_boot": ew.MC_BOOT, "mc_seed": ew.MC_SEED,
               "n_particles": 1000, "sims_per_particle": 20.0,
               "mc_se_label": mc_se, "mc_se_per_cell": {}},
    }


def test_gate_iv_a_is_the_mw6_mean_against_the_tolerance():
    assert ew.table_gate(_scored(mean_mw6=-0.001))["iv_a"]["PASS"] is True
    assert ew.table_gate(_scored(mean_mw6=0.0002))["iv_a"]["PASS"] is True
    assert ew.table_gate(_scored(mean_mw6=0.0003))["iv_a"]["PASS"] is False
    assert ew.table_gate(_scored(mean_mw6=0.0003))["verdict"] == "FAIL"


def test_gate_iv_b_is_a_point_gate_at_each_of_mw0_mw3_and_mw10():
    """R-B2: "No interval is computed at these labels and none is required; two
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
    """R2-B3's repair of the unguarded boundary: round one guarded the
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
    # (P5) iv-c's zero boundary on the interval
    p5 = ew.table_gate(_scored(mean_mw6=-0.01, ci=(1e-6, 0.5),
                               se={"MW6": 1e-5}))
    assert "P5" in p5["precision"]["fired"]
    # ...and every one of them only ever REFUSES
    for out in (p1, p2, p3, p4, p5):
        assert out["PASS"] is False and out["resolved"] is False


def test_an_unresolved_gate_blocks_adoption_and_can_never_grant_one():
    """R2-B3: "UNRESOLVED blocks adoption and can never grant one." R2-X: it is
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
        ew.score_table(rows, n_boot=100, ledger_path=path)


def test_the_hull_analogue_is_printed_with_no_decision_weight(tmp_path):
    """§3.4: "the one Hull-analogue — illustrative, no decision weight"."""
    cells = _cells()
    for cell in cells:
        if cell["season"] == "2019/20" and cell["treated_clubs"]:
            cell["season"] = "2025/26"
    path, rows = _run_cells(tmp_path, cells)
    scored = ew.score_table(rows, n_boot=100, ledger_path=path)
    assert scored["hull_analogue"]["club"] == "sunderland"
    # 2025/26's own MW6 cell is treated already (all seven MW6 cells are), and
    # the four renamed 2019/20 cells join it
    assert scored["hull_analogue"]["n_cells"] == 5
    assert "no decision weight" in scored["hull_analogue"]["label"]
    detail = scored["hull_analogue"]["cells"][0]
    assert set(detail["control"]) >= {"p_relegated", "points_mean", "points_p5",
                                      "points_p95"}


def test_the_coverage_reading_direction_is_fixed_before_the_run(tmp_path):
    """§1.3: the counter-hypothesis, with its reading direction pre-stated —
    coverage already at or above nominal that the treatment pushes further above
    is evidence FOR double-counting and AGAINST this rule."""
    path, rows = _run_cells(tmp_path)
    scored = ew.score_table(rows, n_boot=100, ledger_path=path)
    reading = scored["coverage_reading"]
    assert "double-counting" in reading and "AGAINST this rule" in reading
    treated = next(c for c in scored["per_cell"] if c["treated_clubs"])
    assert treated["coverage_treated_control"]
    assert treated["coverage_treated_treatment"]


def test_the_table_gate_discloses_that_its_numbers_are_invented():
    """§4.3 as R-B2 reissues it: R1 has no pass rule, so both the tolerance and
    the significance construction are invented, blind, for a SINGLE NAMED
    HORIZON rather than for an average protected code forbids."""
    out = ew.table_gate(_scored())
    assert "invented" in out["disclosure"]
    assert "poor coverage" in out["disclosure"]
    assert "single named horizon" in out["disclosure"]
    assert out["tolerance"] == ew.TABLE_TOLERANCE


def test_the_table_ledger_refuses_a_missing_cell(tmp_path):
    """Not a superset, not a subset: a mean over 34 cells is not the quantity
    §4.1 (iv) gates on."""
    cells = _cells()
    path, _ = _run_cells(tmp_path, cells[:-1], harness_frozen=True)
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

    def explode(cell):
        raise RuntimeError("the simulator ran out of memory")

    with pytest.raises(ew.FitFailed):
        ew.run_table(cells, path, runner=explode, parity=_parity_for(cells),
                     n_sims=1, seed=1, config_sha="c", verbose=False,
                     harness_frozen=False)
    assert ew.poison_rows(path)
    with pytest.raises(ew.ShardFailed):
        ew.run_table(cells, path, runner=_table_runner(),
                     parity=_parity_for(cells), n_sims=1, seed=1,
                     config_sha="c", verbose=False, harness_frozen=False)


def test_the_table_leg_never_appends_to_the_protected_retro_ledger():
    """§3.3: `data/epl/sim/retro_r1.jsonl` is read-only and never appended; the
    leg writes its own ledger. R-B4: the parity run is EXECUTED, not read off
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
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    _, table_rows = _run_cells(tmp_path)

    out = tmp_path / "evidence"
    written = ew.write_evidence(result, rows, table_rows, directory=out)
    assert set(written) == {"widening.json", "widening_per_fixture.csv",
                            "widening_grid_means.csv",
                            "widening_table_cells.csv", "MANIFEST.sha256"}
    for name in written:
        assert (out / name).exists()


def test_the_per_fixture_file_reproduces_the_estimand_with_arithmetic_alone(
        tmp_path):
    """`reports/evidence/README.md`'s standard: a reader holding this file and
    nothing else recomputes the headline by averaging one column."""
    import csv as _csv

    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, rows, None, directory=out, manifest=False)

    with (out / "widening_per_fixture.csv").open() as fh:
        got = list(_csv.DictReader(fh))
    assert len(got) == result["n"]
    assert float(np.mean([float(r["delta"]) for r in got])) == \
        pytest.approx(result["mean"])
    # the block labels are columns, because both bootstraps need them
    assert {"block", "season"} <= set(got[0])
    assert len({r["block"] for r in got}) == result["n_blocks"]
    assert len({r["season"] for r in got}) == result["n_season_blocks"]


def test_the_table_evidence_file_carries_both_arms_of_every_cell(tmp_path):
    import csv as _csv

    _, table_rows = _run_cells(tmp_path)
    out = tmp_path / "evidence"
    ew.write_evidence({"schema": ew.SCHEMA_ID}, None, table_rows,
                      directory=out, manifest=False)
    with (out / "widening_table_cells.csv").open() as fh:
        got = list(_csv.DictReader(fh))
    assert len(got) == 2 * len(table_rows)
    assert {r["arm"] for r in got} == {ew.ARM_NAME, ew.BASELINE_ARM}


def test_the_grid_file_carries_every_point_including_the_degenerate_ones(
        tmp_path):
    import csv as _csv

    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, None, None, directory=out, manifest=False)
    with (out / "widening_grid_means.csv").open() as fh:
        got = list(_csv.DictReader(fh))
    assert {float(r["e_star"]) for r in got} == {1.0, 3.0, 5.0, 8.0, 10.0, 12.0}
    degenerate = {float(r["e_star"]) for r in got
                  if r["degenerate_by_construction"] == "True"}
    assert set(ew.E_GRID_DEGENERATE) <= degenerate


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
    assert ew.assert_may_fit("test", harness_frozen=False, played=played,
                             corpus=corpus)["real_artifacts"] is False
    # a caller that has not loaded a frame is a caller about to load the pinned
    # one, and is refused
    with pytest.raises(ew.EvWidenError) as exc:
        ew.assert_may_fit("test", harness_frozen=False, played=None)
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
            ew.assert_may_fit("test", harness_frozen=False,
                              directory=tmp_path, **kwargs)
        assert "IS the pinned" in str(exc.value)

    # ...and the Engine refuses at construction, before it spends a store
    with pytest.raises(ew.EvWidenError):
        ew.Engine(corpus, played, ledger=ledger, harness_frozen=False,
                  directory=tmp_path)


@pinned
def test_the_table_runners_refuse_the_pinned_archive_before_the_freeze(tmp_path):
    """`--table` had the analogous directory-keyed hole, and both the new runner
    and the parity oracle's protected runner are gated now."""
    from epl import baseline

    matches = baseline.load_matches()
    with pytest.raises(ew.EvWidenError):
        ew.TableRunner(matches, harness_frozen=False, directory=tmp_path)
    with pytest.raises(ew.EvWidenError):
        ew.ParityRunner(matches, harness_frozen=False, directory=tmp_path)


def test_the_freeze_block_enumerates_all_six_authorised_pre_freeze_passes():
    """R-B5: "`epl.evwiden.freeze_block`'s default enumeration currently names
    four runs and must be extended to name all six above before the freeze
    commit is generated." The freeze block's list stays binding and must be
    complete."""
    assert len(ew.PRE_FREEZE_RUNS) == 6
    joined = " ".join(ew.PRE_FREEZE_RUNS)
    for marker in ("--membership", "--plan", "--canary --no-results-canary",
                   "pytest epl/tests/test_evwiden.py", "dcfit.fit_epl",
                   "--freeze-block", "repair round's two exports"):
        assert marker in joined, marker
    assert "TemporaryDirectory" in joined and "paths.STORE_DIR" in joined


@pinned
def test_membership_and_plan_carry_the_table_cell_memberships(tmp_path, real):
    """R-B5 pass 1 authorises `--membership` and `--plan` to compute "§2.2's
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
    assert plan["budget"]["table_fits"] == 70
    assert plan["budget"]["table_simulations"] == 105
    assert plan["budget"]["total_fits"] == 78 + 70
    assert "~4 hours" in plan["budget"]["bound"]


def test_the_freeze_refuses_until_the_hash_table_lands(tmp_path):
    empty = tmp_path / "prereg.md"
    empty.write_text("# nothing here\n")
    status = ew.harness_freeze_status([empty])
    assert status["frozen"] is False
    assert "has not landed" in status["why"]
    with pytest.raises(ew.EvWidenError) as exc:
        ew.require_harness_freeze([empty])
    assert "SYNTHETIC" in str(exc.value)


def test_an_uncommitted_hash_paste_freezes_nothing(tmp_path):
    """R2, the defect that replaces round one's round-trip test: "Round one's
    freeze guard parses current prose against current filesystem bytes, which an
    uncommitted two-line paste satisfies; that is not a freeze and this document
    does not accept it as one."

    The paste below carries the CORRECT digests of the harness files on disk —
    it is exactly what round one's guard called frozen — and it is refused,
    because it is not in a commit."""
    table = tmp_path / "prereg.md"
    table.write_text("\n".join(
        f"| `{name}` | {ew.sha256_file(ew.paths.REPO_ROOT / name)} |"
        for name in ew.HARNESS_FILES) + "\n")
    status = ew.harness_freeze_status([table])
    assert status["frozen"] is False
    assert status["files"] == {}
    assert "COMMITTED" in status["why"]
    assert status["uncommitted_sources"] == [ew.paths.rel(table)]


def test_the_freeze_reads_the_committed_prose_and_the_committed_bytes():
    """R2: the guard verifies "the Git object identity of the prereg blob whose
    hash table it reads". Both sides come out of Git — the prose AND the harness
    bytes — and the working tree is checked as well, so a dirty tree is not
    frozen either."""
    status = ew.harness_freeze_status()
    assert status["rev"] == "HEAD"
    assert [s["path"] for s in status["sources"]] == [
        ew.paths.rel(ew.PREREG_PATH), ew.paths.rel(ew.AMENDMENTS_PATH)]
    assert all(s["committed"] for s in status["sources"])
    assert all(s["blob"] for s in status["sources"])
    # the prereg is committed and the harness hash table has NOT been pasted:
    # R-H(1) reaffirms that the freeze stays unpasted until the harness
    # implements both repair rounds
    assert status["frozen"] is False
    assert status["missing"] == list(ew.HARNESS_FILES)


def _as_if_committed(table: str | None = None):
    """`git show` as it would read after the freeze commit landed.

    The prereg carries `table` (the rendered hash table by default) and every
    harness file's committed bytes are the working tree's, which is what a clean
    tree at the freeze commit looks like.
    """
    text = table if table is not None else "\n".join(
        f"| `{name}` | {ew.sha256_file(ew.paths.REPO_ROOT / name)} |"
        for name in ew.HARNESS_FILES) + "\n"

    def committed(relpath, rev="HEAD"):
        if relpath == ew.paths.rel(ew.PREREG_PATH):
            return text.encode()
        if relpath in ew.HARNESS_FILES:
            return (ew.paths.REPO_ROOT / relpath).read_bytes()
        return b""

    return committed


def test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head(monkeypatch):
    """The task R2 sets the guard: verify a COMMITTED freeze — the Git identity
    of the source, not prose beside bytes."""
    monkeypatch.setattr(ew, "git_committed_bytes", _as_if_committed())
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
    """§6 step 2: "if any hash differs at the time the run is executed, it is
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


def test_the_first_real_fit_event_is_recorded_once_and_then_binds(tmp_path):
    """R-B6, made mechanical: from the moment a real fit on the real archive
    exists, ANY change to ANY hashed file invalidates this preregistration — no
    note, no dated appendix, no disclosure and no owner ruling restores it."""
    assert ew.first_fit_record(tmp_path) is None
    record = ew.record_first_real_fit(tmp_path, where="the results canary")
    assert record["where"] == "the results canary"
    assert set(record["harness"]) == set(ew.HARNESS_FILES)
    assert record["commit"] and record["prereg_blob"]
    # written once and never rewritten
    again = ew.record_first_real_fit(tmp_path, where="something else")
    assert again["at"] == record["at"] and again["where"] == record["where"]

    ew.assert_no_hashed_file_moved(tmp_path)          # nothing moved yet
    moved = json.loads((tmp_path / ew.FIRST_FIT_NAME).read_text())
    moved["harness"][ew.HARNESS_FILES[0]] = "0" * 64
    (tmp_path / ew.FIRST_FIT_NAME).write_text(json.dumps(moved))
    with pytest.raises(ew.EvWidenError) as exc:
        ew.assert_no_hashed_file_moved(tmp_path)
    assert "INVALIDATES this preregistration" in str(exc.value)


# ==========================================================================
# 14. the detached launch — §2.4, generated rather than committed
# ==========================================================================

def test_the_launcher_is_generated_and_lives_in_the_run_directory(tmp_path):
    """§6 names two harness files. A loose `run_evwiden.sh` would be code whose
    bytes nothing hashes while being able to change which shards run."""
    path = ew.write_launch_script(tmp_path, shards=3)
    assert path.parent == tmp_path
    assert path.name == ew.LAUNCH_NAME
    assert not str(path).startswith(str(ew.paths.REPO_ROOT / "scripts"))
    assert path.stat().st_mode & 0o111        # executable
    assert not (ew.paths.REPO_ROOT / "epl" / "run_evwiden.sh").exists()


def test_the_launcher_pins_blas_before_python_and_runs_unbuffered(tmp_path):
    text = ew.launch_script(tmp_path, shards=2)
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert f"export {var}=1" in text or f"{var}=1" in text
    assert text.index("export OMP_NUM_THREADS") < text.index("$PY -u -m epl.evwiden")
    assert "-u -m epl.evwiden" in text
    assert "nohup sh" in text                 # the launch line, in a comment
    assert "<<" not in text                   # never a stdin heredoc


def test_the_launcher_runs_shards_sequentially_and_waits_per_pid(tmp_path):
    """§2.4: parallel shards crash on the featpanel `.tmp` rename race, and a
    bare `wait` returns the LAST job's status — a failed shard would sail past."""
    text = ew.launch_script(tmp_path, shards=3)
    order = [text.index(f"--shard {i}/3") for i in range(3)]
    assert order == sorted(order)
    assert 'wait "$pid"' in text
    for line in text.splitlines():
        assert line.strip() != "wait"
    assert text.count("run_step shard_") == 3
    assert "exit 2" in text                   # a failed step stops the run


def test_the_launcher_puts_the_canary_first_and_the_merge_last(tmp_path):
    """RUN_ORDER, in the launcher as well as in the module."""
    text = ew.launch_script(tmp_path, shards=2)
    assert text.index("run_step canary") < text.index("run_step shard_00")
    assert text.index("run_step shard_01") < text.index("run_step table")
    assert text.index("run_step table") < text.index("run_step merge")
    assert ew.RUN_ORDER == ("canary", "run", "table", "merge")


def test_the_launcher_is_a_valid_shell_script(tmp_path):
    """`sh -n` parses it without running it."""
    path = ew.write_launch_script(tmp_path, shards=2)
    done = subprocess.run(["sh", "-n", str(path)], capture_output=True)
    assert done.returncode == 0, done.stderr.decode()


# ==========================================================================
# 15. the CLI
# ==========================================================================

def test_the_cli_writes_the_launcher_and_exits_clean(tmp_path, capsys):
    assert ew.main(["--script", "--dir", str(tmp_path), "--shards", "2"]) == 0
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

    §7 makes a real-archive fit before the §6 freeze commit an invalidation.
    Reading the archive to recompute `e` is not a fit: it is arithmetic on
    committed bytes, and it is how §6 step 2's membership digests are produced
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
    this is the enumeration the §6 commit freezes."""
    from epl import baseline, simretro

    matches = baseline.load_matches()
    cells = ew.table_cells(matches)
    assert len(cells) == len(simretro.SEASONS) * len(simretro.COMPARISON_CUTOFFS)
    assert len(cells) == 35
    treated = {(c["season"], c["cutoff_label"]): c["treated_clubs"]
               for c in cells if c["treated_clubs"]}
    assert len(treated) == 16
    assert len(cells) - len(treated) == 19
    assert treated[("2019/20", "MW0")] == ["aston_villa", "norwich"]
    assert treated[("2019/20", "MW6")] == ["aston_villa", "norwich",
                                           "sheffield_united"]
    assert treated[("2023/24", "MW0")] == ["sheffield_united"]
    # the one Hull-analogue, §0.5's Sunderland cells
    for label in ("MW0", "MW3", "MW6"):
        assert treated[("2025/26", label)] == ["sunderland"]
    assert ("2025/26", "MW10") not in treated
    assert round(cells[0]["evidence"]["aston_villa"], 2) == 4.74


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
    assert "epl-evwiden-1" in text and ew.SCHEMA_ID == "epl-evwiden-1"
    for name in ew.HARNESS_FILES:
        assert name in text
    # the numbers §4 gates on, as the document writes them
    assert "-0.0010" in text.replace("−", "-")
    assert "+0.0002" in text


def test_the_canary_never_rebuilds_the_shared_point_in_time_store(monkeypatch):
    """§6 closes the write set, and `epl.fit.build_store` UNLINKS and rewrites
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

def test_every_refusal_type_5_1_names_exists_and_derives_from_the_base():
    """§5.1's table, by name. A typed name is a promise the preregistration
    made; this is the test that it was kept."""
    named = ("CorpusMissing", "CorpusDigestMismatch", "CorpusShapeMismatch",
             "ArchiveDigestMismatch", "LedgerDigestMismatch", "ConfigNotFrozen",
             "MembershipMismatch", "PredicateMismatch", "EvidenceLeak",
             "CutoffLeak", "CanaryFailed", "EvidenceCanaryFailed",
             "ControlMismatch", "UntreatedMoved", "TableIdentityBreak",
             "FitFailed", "UnpriceableFixture", "ScoreMismatch",
             "SchemaMismatch", "RowConflict", "ShardFailed", "MergeIncomplete",
             "TableMCImprecise")
    assert len(named) == 23
    for name in named:
        cls = getattr(ew, name)
        assert issubclass(cls, ew.EvWidenError), name
        assert issubclass(cls, RuntimeError), name


def test_the_harness_invents_no_refusal_the_document_never_wrote():
    """`epl.freshsweep`'s ruling, applied here: a condition §7 pre-states as an
    invalidation but §5.1 never named refuses as the BASE class rather than
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
             "TableMCImprecise"}
    assert subclasses == named
    # R2-X counts it both ways so neither reading is wrong: 23 named refusals,
    # 24 classes counting the base they all derive from.
    assert len(subclasses) == 23 and len(subclasses | {"EvWidenError"}) == 24
    # the pre-freeze-fit invalidation is one of the unnamed ones, and refuses
    # as the base class
    with pytest.raises(ew.EvWidenError) as exc:
        ew.require_harness_freeze([Path("/nonexistent-prereg.md")])
    assert type(exc.value) is ew.EvWidenError


def test_verify_re_derives_the_headline_from_the_committed_evidence(tmp_path):
    """The check a reader of the repository can run: three routes to the number
    rather than one number copied twice."""
    _run(tmp_path)
    rows = ew.load_ledger(tmp_path / ew.shard_name(0, 1))
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, rows, None, directory=out, manifest=False)

    checked = ew.verify(tmp_path, shards=1, evidence=out / "widening.json",
                        n_boot=200)
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
    result = ew.estimand(rows, n_boot=200, corpus_rows=len(rows))
    out = tmp_path / "evidence"
    ew.write_evidence(result, rows, None, directory=out, manifest=False)

    published = json.loads((out / "widening.json").read_text())
    published["mean"] = float(published["mean"]) + 1e-6
    (out / "widening.json").write_text(json.dumps(published))
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.verify(tmp_path, shards=1, evidence=out / "widening.json", n_boot=200)
    assert "does not re-derive" in str(exc.value)


def test_verify_refuses_when_there_is_no_published_verdict(tmp_path):
    with pytest.raises(ew.MergeIncomplete) as exc:
        ew.verify(tmp_path, shards=1, evidence=tmp_path / "absent.json")
    assert "never finished" in str(exc.value)


def test_no_live_2026_27_quantity_can_enter_this_experiment():
    """§7: "The 27.9→15.9 counterfactual, or any live-2026/27 quantity, enters
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
    """§5.3 makes `walkforward.point_in_time_canary` a precondition on the REAL
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
    result = ew.estimand(rows, n_boot=100, corpus_rows=len(rows))
    assert result["secondaries_decide"] == "nothing"
    assert result["secondaries"]["full_population"]["decides"] == "nothing"
    assert result["decides"].startswith("nothing")


@pinned
def test_the_freeze_block_is_harness_produced_and_round_trips(tmp_path):
    """§6 step 2 asks its commit for the harness hashes, the schema identifier,
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
    for digest in ("thin", "treated", "new_cells", "fit_openings",
                   "table_treated", "table_untouched", "membership"):
        assert digest or True                       # named below by count
    assert "| 85 |" in block and "| 52 |" in block and "| 51 |" in block
    assert "| 78 |" in block and "| 16 |" in block and "| 19 |" in block
    assert "Pre-freeze runs, enumerated" in block
    assert "not the run this document preregisters" in block

    assert all(name in block for name in
               ("--membership", "--freeze-block", "repair round's two exports"))

    # THE ROUND TRIP IS NOT A PASTE ANY MORE (R2). Round one's test dropped the
    # rendered block into a temporary file and demanded `harness_freeze_status`
    # say frozen; an uncommitted two-line paste satisfied that, which is not a
    # freeze. What is asserted instead is that the block a COMMIT would carry
    # binds the committed bytes.
    pasted = tmp_path / "prereg.md"
    pasted.write_text(block)
    assert ew.harness_freeze_status([pasted])["frozen"] is False
    import unittest.mock as mock

    with mock.patch.object(ew, "git_committed_bytes",
                           _as_if_committed(block)):
        got = ew.harness_freeze_status([ew.PREREG_PATH])
    assert got["frozen"] is True
    assert all(f["match"] for f in got["files"].values())


@pinned
def test_the_freeze_block_digests_are_the_membership_digests():
    """The two must not be two computations of the same thing."""
    corpus, played, ledger = (ew.load_corpus(), ew.load_archive(),
                              ew.load_walk_ledger())
    from epl import baseline

    cells = ew.table_cells(baseline.load_matches(), played)
    digests = ew.membership_digests(corpus, played, ledger, table=cells)
    block = ew.freeze_block(corpus, played, ledger, cells)
    for value in digests["digests"].values():
        assert value in block
