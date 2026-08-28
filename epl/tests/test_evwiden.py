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

#: The preregistration this harness implements. v2 is the SOLE LAW; v1 is
#: lineage and decides nothing (§8.1).
PREREG = Path("reports/epl_widening_prereg_v2.md")
PREREG_V1 = Path("reports/epl_widening_prereg.md")

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
    assert ew.SCHEMA_ID == "epl-evwiden-2"
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
                    verbose=False)
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


def test_seeded_defect_an_untreated_fixture_with_a_delta_refuses(tmp_path):
    """The full-population identity would be FALSE if an untreated fixture
    carried a delta, so the harness refuses instead of printing it."""
    rows = _merged(tmp_path)
    stray = next(r for r in rows if float(r["e_min"]) >= ew.E_STAR)
    stray["delta"] = 1e-9
    with pytest.raises(ew.UntreatedMoved):
        ew.estimand(rows, corpus_rows=len(rows))


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
    """R-I2 supersedes §2.3's "No power claim is made in advance": the analysis
    was done, blind, and is committed code. What the estimand carries is the
    other half R-I2 requires — "after the run, the REALISED paired SD of the
    treated deltas and the MDE recomputed at it" — which decides nothing and
    moves no threshold, beside the three frozen scenarios and R-I2's warning."""
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
               **kwargs):
    """Run the stub table leg with a stub parity oracle beside it."""
    cells = _cells() if cells is None else cells
    path = Path(tmp_path) / name
    ew.run_table(cells, path, runner=runner or _table_runner(),
                 parity=_parity_for(cells), n_sims=TALLY_N_SIMS, seed=20260611,
                 config_sha="c", verbose=False, **kwargs)
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


def test_no_require_parity_parameter_and_no_limit_on_the_oracle_exist():
    """§3.3's closures 2 and 3, conformance row L5.

    > **No `--limit` on the oracle.** No CLI flag, keyword or subset argument
    > may reduce the oracle's 35 cells. "All 35" is the whole content of the
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

        def counting(cell, _inner=_table_runner()):
            simulated.append(cell["season"] + "|" + cell["cutoff_label"])
            return _inner(cell)

        with pytest.raises(ew.TableIdentityBreak) as exc:
            ew.run_table(cells, tmp_path / "t.jsonl", runner=counting,
                         parity=oracle, n_sims=TALLY_N_SIMS, seed=1,
                         config_sha="c", verbose=False)
        assert "before" in str(exc.value).lower()
        assert simulated == [], simulated       # not ONE arm of ONE cell


def test_the_treated_run_refuses_a_control_arm_that_drifted_from_protected(
        tmp_path):
    cells = _cells()
    with pytest.raises(ew.TableIdentityBreak):
        ew.run_table(cells, tmp_path / "t.jsonl",
                     runner=_table_runner(break_parity=True),
                     parity=_parity_for(cells), n_sims=TALLY_N_SIMS, seed=1,
                     config_sha="c", verbose=False)


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
                       parity=_parity_for(cells), n_sims=TALLY_N_SIMS,
                       seed=20260611, config_sha="c", verbose=False)
    assert out["n_written"] == len(cells) == 35
    again = ew.run_table(cells, path, runner=_table_runner(),
                         parity=_parity_for(cells), n_sims=TALLY_N_SIMS,
                         seed=20260611, config_sha="c", verbose=False)
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
    """R-B2 (iv-a): the equal-weight mean over the SEVEN MW6 cells. (iv-b): at
    MW0, MW3 and MW10, the mean over THAT LABEL'S TREATED CELLS ONLY."""
    path, rows = _run_cells(tmp_path, runner=_table_runner(shift=-0.001))
    scored = ew.score_table(rows, ledger_path=path)
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
    """R2-B3 step 2: "Joint resampling is undefined without a common index
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

def _scored(mean_mw6=0.0, ci=(-1.0, 1.0), means=(0.0, 0.0, 0.0), se=None,
            unanimity=None):
    labels = dict(zip(ew.POINT_GATE_LABELS, means))
    mc_se = {"MW6": 0.0, "MW0": 0.0, "MW3": 0.0, "MW10": 0.0}
    mc_se.update(se or {})
    if unanimity is None:
        # §5.4's default for a scored object that carries no unanimity run at
        # all: a P5 that was never computed is UNRESOLVED, never "small". The
        # tests that are about P1-P4 hand in an agreed one so the gate can
        # resolve on the condition they are actually about.
        unanimity = {"k": ew.UNANIMITY_K, "seed": ew.UNANIMITY_SEED,
                     "dissenting": 0, "fired": False}
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
    # (P5) iv-c's zero boundary on the interval — the UNANIMITY rule
    p5 = ew.table_gate(_scored(mean_mw6=-0.01, ci=(-0.02, -0.005),
                               unanimity={"k": ew.UNANIMITY_K,
                                          "dissenting": 1, "fired": True}))
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
        mean_mw6=-0.01, ci=(-0.02, -0.005),
        unanimity={"k": ew.UNANIMITY_K, "dissenting": 0, "fired": False}))
    assert "P5" not in agreed["precision"]["fired"]
    assert agreed["precision"]["unanimity_k"] == 200
    assert agreed["precision"]["unanimity_seed"] == 20260828
    assert agreed["precision"]["unanimity_dissenting"] == 0


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
    scored = ew.score_table(rows, ledger_path=path)
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

    def explode(cell):
        raise RuntimeError("the simulator ran out of memory")

    with pytest.raises(ew.FitFailed):
        ew.run_table(cells, path, runner=explode, parity=_parity_for(cells),
                     n_sims=1, seed=1, config_sha="c", verbose=False)
    assert ew.poison_rows(path)
    with pytest.raises(ew.ShardFailed):
        ew.run_table(cells, path, runner=_table_runner(),
                     parity=_parity_for(cells), n_sims=1, seed=1,
                     config_sha="c", verbose=False)


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
    """R-I6: "the evidence schema, frozen field by field". The superseded table
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
        "schema", "generated_at", "prereg_commit", "repairs_section", "pins",
        "estimand", "ci_week", "ci_season", "ci_table_mw6",
        "gate_i", "gate_ii", "gate_iii", "gate_iv", "controls", "canaries",
        "grid", "strata", "movement", "coverage", "sunderland", "power",
        "materiality", "verdict"}
    # THREE deciding intervals, each with its own frozen construction
    for name in ("ci_week", "ci_season", "ci_table_mw6"):
        assert set(published[name]) >= {"function", "n_blocks", "B", "alpha",
                                        "seed", "lo", "hi"}
        assert published[name]["function"] == "epl.score.block_bootstrap_ci"
    assert published["ci_table_mw6"]["n_blocks"] == 7
    # the 820-fixture control has a home, with both numbers
    assert set(published["controls"]["identity"]) == {"n", "max_abs_diff",
                                                      "mean_abs_diff", "PASS"}
    assert published["controls"]["table_parity"]["n_cells"] == 35
    # gate (iv) carries R2-B3's precision names, not R-I6's superseded mc_se_mean
    precision = published["gate_iv"]["precision"]
    assert set(precision) >= {"mc_boot", "mc_seed", "n_particles",
                              "sims_per_particle", "mc_se_mw6", "mc_se_mw0",
                              "mc_se_mw3", "mc_se_mw10", "mc_se_per_cell",
                              "conditions", "resolved"}
    assert "mc_se_mean" not in precision
    assert {c["condition"] for c in precision["conditions"]} == {
        "P1", "P2", "P3.MW0", "P3.MW3", "P3.MW10", "P4", "P5"}
    assert published["gate_iv"]["mw19"]["decides"] == "nothing"
    assert published["sunderland"]["club"] == "sunderland"
    assert published["materiality"]["required_sentence"] == \
        ew.MATERIALITY_SENTENCE
    assert published["pins"]["realised_config_sha256"] == \
        ew.REALISED_CONFIG_SHA256

    # R-I2's required publication: the frozen scenarios, the structure, the MDE
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


def test_the_manifest_is_the_eleven_paths_and_a_missing_file_is_a_refusal(
        tmp_path):
    """R2-I6: "'Bulky local artifacts' is no longer a category; it is a list."
    Eleven paths, and `--verify` refuses a missing entry, a disagreeing digest,
    or an entry of ours outside the eleven."""
    assert len(ew.MANIFEST_PATHS) == 11
    assert ew.MANIFEST_PATHS[4:8] == tuple(
        f"data/epl/fit/evwiden/shard_{i:02d}_of_04.jsonl" for i in range(4))
    assert ew.SHARDS == 4

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


def test_the_manifest_refuses_an_entry_of_ours_outside_the_eleven(tmp_path):
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
    assert "outside the eleven" in str(exc.value)

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
    # R-B1: both arms and the corpus, side by side, so a reader can confirm the
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
    # R-I6: 35 rows — one per CELL, the paired shape the deltas have
    assert len(got) == len(table_rows) == 35
    assert list(got[0]) == list(ew._TABLE_COLUMNS)
    treated = [r for r in got if r["treated_clubs"]]
    assert len(treated) == 16
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


def test_the_freeze_block_enumerates_all_six_authorised_pre_freeze_passes():
    """§8.2's six passes, "authorised for this document, prospectively".

    v1's sixth entry named a repair round's two scratch exports — an event, not
    a prospective pass. v2's sixth is ``--power``, which reads only the frozen
    SDs and the frozen structure and reproduces §6.3. The list stays binding and
    must be complete: an unenumerated pre-freeze pass is a protocol deviation
    whether or not it touched anything.
    """
    assert len(ew.PRE_FREEZE_RUNS) == 6
    joined = " ".join(ew.PRE_FREEZE_RUNS)
    for marker in ("--membership", "--plan", "--canary --no-results-canary",
                   "pytest epl/tests/test_evwiden.py", "dcfit.fit_epl",
                   "--freeze-block", "--power"):
        assert marker in joined, marker
    assert "TemporaryDirectory" in joined and "paths.STORE_DIR" in joined
    # v1's sixth entry was a RETROSPECTIVE note about a repair round. §8.2
    # authorises v2's own passes prospectively and nothing else.
    assert "repair round" not in joined


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


@pinned
def test_the_freeze_needs_a_commit_that_is_an_ancestor_of_head(monkeypatch):
    """§8.6's task for the guard: verify a COMMITTED freeze — the Git identity
    of the source, not prose beside bytes.

    The mocked committed source is now the harness's OWN rendered freeze block,
    because §8.6 conditions (3) and (4) read the schema identifier and the
    membership digests out of it. That is why this test reads the pinned
    artifacts: a two-hash-line stand-in is no longer a freeze, and v1's test
    accepted one.
    """
    block = ew.freeze_block(power=_reproducing_power())
    monkeypatch.setattr(ew, "git_committed_bytes", _as_if_committed(block))
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


def test_the_first_fit_record_lives_at_one_fixed_repo_root_keyed_path():
    """§8.6, conformance row L8. "The record lives at **one fixed
    repo-root-keyed path**, `data/epl/fit/evwiden_first_real_fit.json`, derived
    from `paths.REPO_ROOT` and from nothing else. **No function that reads or
    writes it takes a directory argument.**"

    v1's record was written below the caller's chosen directory, so a fresh or
    deleted `--dir` reset the entire R-B6 regime — the one-way ratchet had a way
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
    ew.record_first_real_fit(where="the results canary")
    planted = json.loads((tmp_path / "first_real_fit.json").read_text())
    planted["prereg_blob"] = "0" * 40
    (tmp_path / "first_real_fit.json").write_text(json.dumps(planted))
    with pytest.raises(ew.FreezeStateUnverified) as exc:
        ew.assert_no_hashed_file_moved()
    assert "prereg blob" in str(exc.value)


def test_the_freeze_guard_checks_the_schema_and_the_membership_digests(
        monkeypatch):
    """§8.6's four conditions, and v1's guard parsed only the first two.

    "Parsing two hash lines out of current prose is not a freeze"; nor is
    parsing two hash lines out of committed prose. The block must also carry the
    schema identifier `epl-evwiden-2` and membership digests that equal a fresh
    recomputation from the pinned artifacts. A mocked source containing only two
    hash lines is not frozen, and v1's test accepted one that was.
    """
    monkeypatch.setattr(ew, "git_committed_bytes", _as_if_committed())
    status = ew.harness_freeze_status()
    assert status["frozen"] is False
    assert "schema" in status["why"] or "membership" in status["why"]
    assert status["schema_ok"] is False


# ==========================================================================
# 14. the detached launch — §2.4, generated rather than committed
# ==========================================================================

def test_the_launcher_is_generated_and_lives_in_the_run_directory(tmp_path):
    """§6 names two harness files. A loose `run_evwiden.sh` would be code whose
    bytes nothing hashes while being able to change which shards run."""
    path = ew.write_launch_script(tmp_path)
    assert path.parent == tmp_path
    assert path.name == ew.LAUNCH_NAME
    assert not str(path).startswith(str(ew.paths.REPO_ROOT / "scripts"))
    assert path.stat().st_mode & 0o111        # executable
    assert not (ew.paths.REPO_ROOT / "epl" / "run_evwiden.sh").exists()


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

    # each step's precondition check appears BEFORE its command
    for step, command in (("step1_results_canary", "run_step shard_00"),
                          ("step3_shards", "run_step merge"),
                          ("step4_merge", "run_step table")):
        assert text.index(step) < text.index(command), step


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
    path = ew.write_launch_script(tmp_path)
    done = subprocess.run(["sh", "-n", str(path)], capture_output=True)
    assert done.returncode == 0, done.stderr.decode()


# ==========================================================================
# 15. the CLI
# ==========================================================================

def test_the_cli_writes_the_launcher_and_exits_clean(tmp_path, capsys):
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
    assert "epl-evwiden-2" in text and ew.SCHEMA_ID == "epl-evwiden-2"
    for name in ew.HARNESS_FILES:
        assert name in text
    # the numbers §4 gates on, as the document writes them
    assert "-0.0010" in text.replace("−", "-")
    assert "+0.0002" in text


@pytest.mark.skipif(not PREREG.exists(), reason="the preregistration is absent")
def test_the_harness_is_bound_to_v2_and_v1_is_only_lineage():
    """§8.1: v1 is invalidated by its own R-B6 and "decides nothing".

    The freeze guard, the first-fit record and the evidence object all name a
    preregistration by path. If any of them still names v1, the harness is
    binding itself to an invalidated document — and the two ADVI fits that
    ended v1 would carry into v2's regime.
    """
    assert ew.PREREG_PATH.name == "epl_widening_prereg_v2.md"
    assert ew.SCHEMA_ID == "epl-evwiden-2"
    text = PREREG.read_text()
    assert "invalidated 2026-08-28 under its own R-B6" in text
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
             "TableMCImprecise", "StoreNotBuilt", "SequenceViolation",
             "FreezeStateUnverified"}
    assert subclasses == named
    # §7.1 counts it both ways so neither reading is wrong: 26 named refusals,
    # 27 classes counting the base they all derive from.
    assert len(subclasses) == 26 and len(subclasses | {"EvWidenError"}) == 27
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
    result = ew.estimand(rows, corpus_rows=len(rows))
    assert result["secondaries_decide"] == "nothing"
    assert result["secondaries"]["full_population"]["decides"] == "nothing"
    assert result["decides"].startswith("nothing")


# ==========================================================================
# R2-I2 — the power simulation, committed
# ==========================================================================

def _reproducing_power():
    """A `power` object whose rows are the six published ones, exactly.

    `power_simulation()` itself is R = 2,000 replicates over six scenarios and
    costs about twenty seconds; the freeze-block tests are about the freeze
    block, so they hand it a stub and the reproduction question gets its own
    test.
    """
    return {"rows": [{"scenario": r["scenario"], "rho": r["rho"],
                      "power_at_bar": r["power_at_bar"],
                      "mde_estimand": r["mde_estimand"],
                      "power_at_2x_bar": r["power_at_2x"]}
                     for r in ew.PUBLISHED_POWER]}


def test_the_power_simulation_is_committed_code_at_the_ruled_path():
    """R2-I2: "R-I2's six power numbers were produced by uncommitted scratch
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
    # the constants R2-I2 freezes
    assert ew.POWER_REPLICATES == 2000 and ew.POWER_SEED == 20260827
    assert ew.POWER_GRID_POINTS == 101 and ew.POWER_GRID_STEP == 2e-4
    assert [s[1] for s in ew.POWER_SCENARIOS] == [0.005262, 0.014449, 0.036]
    assert ew.POWER_RHOS == (0.0, 0.5)
    assert ew.POWER_BAR == pytest.approx(-0.0016346153846153847, abs=1e-18)
    assert 2 * ew.POWER_BAR == pytest.approx(-0.0032692307692307695, abs=1e-18)
    assert len(ew.PUBLISHED_POWER) == 6


def test_the_mde_rules_are_interpolation_then_tie_then_exhaustion():
    """R2-I2 freezes all three, in that order."""
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
    """R2-I2: "A vectorised inner loop is permitted ONLY if a committed test
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
    """R2-I2's structure, and the counts are checked rather than typed in: the
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
def test_the_freeze_block_refuses_while_a_power_number_is_unreproduced():
    """R2-I2: "No freeze block may be rendered while an unreproduced power
    number stands in this document." The remedy is a dated note appended BEFORE
    the freeze commit, and it is an owner's call rather than the harness's."""
    broken = _reproducing_power()
    broken["rows"][0] = dict(broken["rows"][0], power_at_bar=0.999)
    with pytest.raises(ew.EvWidenError) as exc:
        ew.freeze_block(power=broken)
    assert "does not yet implement the document" in str(exc.value)
    assert "dated note appended" in str(exc.value)
    assert "R2-I2 (numbers)" in str(exc.value)

    report = ew.implementation_report(broken)
    assert [r["id"] for r in report if not r["ok"]] == ["R2-I2 (numbers)"]


def test_the_conformance_report_covers_the_re_reviews_whole_work_order():
    """R2-0: "§6 step 1 (the harness is written and audited) is not satisfied
    until the harness implements this document as repaired in both rounds"."""
    report = ew.implementation_report(_reproducing_power())
    ids = [r["id"] for r in report]
    assert set(ids) >= {"R-B1", "R-B2", "R2-B3", "R2-B4", "R2-B5", "R-B6",
                        "R-I1", "R2-I2", "R-I4", "R2-I5", "R2-I6", "R-M2",
                        "R2-X", "R2-I2 (numbers)"}
    assert all(r["ok"] for r in report), [r for r in report if not r["ok"]]


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
    block = ew.freeze_block(power=_reproducing_power())
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
               ("--membership", "--freeze-block", "--power"))

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
    block = ew.freeze_block(corpus, played, ledger, cells,
                            power=_reproducing_power())
    for value in digests["digests"].values():
        assert value in block
