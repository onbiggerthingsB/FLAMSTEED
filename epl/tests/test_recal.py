"""A8 — `dc_1x2_recal`, the match-only shadow challenger, held to the entry
that pre-stated it.

    PYTHONPATH=src:. .venv/bin/python -m pytest epl/tests/test_recal.py -q

A8 (``reports/epl_sim_amendments.md``) freezes a RULE and not a number: the
transform class closed at one parameter, the corpus by sha256, one objective,
one deterministic procedure, and a constant recorded to twelve decimals. These
tests hold the code to that entry, and they are shaped around the two things
the entry says are easy to get wrong:

* **A four-decimal control cannot tell two different inputs apart.** A8 item 4
  measures it: the rendered triple ``0.7639 / 0.1618 / 0.0743`` and the
  published one ``0.763900 / 0.161750 / 0.074350`` transform to vectors that
  render IDENTICALLY at 4dp and differ at the sixth decimal. So every control
  here asserts at 1e-9 or better, on the file's own probabilities, and never on
  a rendered string.
* **A verification that skips is worse than one nobody ran.** The corpus is
  checked by digest BEFORE any fit, and its absence is a typed refusal.

CI HAS NO ``data/``. Everything below builds its own corpus, its own rows and
its own season; the handful of tests that read the pinned parquet or the
preserved MW0 bundle are guarded on the file's existence and skip.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl import matchboard, recalfit

#: The pinned corpus. Present on the machine that fitted the constant and
#: nowhere else, so every test that reads it is guarded.
PINNED_CORPUS = Path("data/epl/fit/walkforward_predictions.parquet")

#: A8 item 3 — the published Arsenal–Coventry MW0 marginals, which are A7's
#: exact counts 15278 / 3235 / 1487 over 20,000.
ARSENAL_COVENTRY = {"home": 0.763900, "draw": 0.161750, "away": 0.074350}

#: ...and the vector A8 pre-states the frozen `a` sends them to.
ARSENAL_COVENTRY_RECAL = {"home": 0.732099900325, "draw": 0.179273332146,
                          "away": 0.088626767529}


# ==========================================================================
# 1. the transform — closed at one parameter, and exact
# ==========================================================================

def test_the_transform_is_the_closed_one_parameter_power_law():
    """A8 (b): ``q_i = p_i^a / (p_home^a + p_draw^a + p_away^a)``.

    Hand-computed rather than re-expressed: with `p = (0.5, 0.3, 0.2)` and
    `a = 2` the numerators are `0.25, 0.09, 0.04` and the denominator `0.38`.
    """
    q = recalfit.transform({"home": 0.5, "draw": 0.3, "away": 0.2}, 2.0)
    assert q["home"] == pytest.approx(0.25 / 0.38, abs=1e-15)
    assert q["draw"] == pytest.approx(0.09 / 0.38, abs=1e-15)
    assert q["away"] == pytest.approx(0.04 / 0.38, abs=1e-15)


def test_a_equals_one_is_the_identity():
    """A8 (b) says so in one line, and it is the only value of `a` at which the
    challenger and the published law are the same forecast."""
    p = {"home": 0.7639, "draw": 0.1618, "away": 0.0743}
    q = recalfit.transform(p, 1.0)
    total = sum(p.values())
    for k in matchboard.OUTCOMES:
        assert q[k] == pytest.approx(p[k] / total, abs=1e-15)


def test_the_transform_renormalises_to_one():
    """A8 item 5: `q_home + q_draw + q_away = 1` within 1e-9, at every `a` this
    project could ever freeze."""
    p = {"home": 0.763900, "draw": 0.161750, "away": 0.074350}
    for a in (0.25, 0.5, recalfit.A, 1.0, 1.5, 2.0, 4.0):
        q = recalfit.transform(p, a)
        assert abs(sum(q.values()) - 1.0) <= 1e-9, a


def test_a_non_finite_probability_is_refused():
    """A NaN through a power law comes out a NaN, renormalises to a NaN, and
    scores as a NaN — a row of three NaNs in an append-only ledger is a row
    nobody can ever check. It is refused at the door."""
    for bad in (float("nan"), float("inf"), -1.0):
        with pytest.raises(recalfit.RecalError):
            recalfit.transform({"home": bad, "draw": 0.3, "away": 0.2}, recalfit.A)
    # ...and so is a non-finite exponent, for the same reason
    with pytest.raises(recalfit.RecalError):
        recalfit.transform({"home": 0.5, "draw": 0.3, "away": 0.2},
                           float("nan"))
    # a zero cell is refused too: `0 ** a` is 0 for every a > 0, so the cell can
    # never come back, and `ln 0` is what the fit's own derivative would take.
    with pytest.raises(recalfit.RecalError):
        recalfit.transform({"home": 0.0, "draw": 0.5, "away": 0.5}, recalfit.A)


def test_the_transform_cannot_reorder_the_outcomes():
    """PROVED, not sampled: `q_i / q_j = (p_i / p_j)^a`, and `x -> x^a` is
    strictly increasing on `(0, inf)` for every `a > 0`.

    So a temperature can flatten a forecast or sharpen it and can never say a
    different thing about which outcome is likelier. The identity is asserted
    on the numbers as well as argued in the docstring, because the identity is
    what the code either has or does not.
    """
    rng = np.random.default_rng(20260825)
    for _ in range(200):
        raw = rng.dirichlet((0.6, 0.6, 0.6))
        p = dict(zip(matchboard.OUTCOMES, raw))
        a = float(rng.uniform(0.2, 3.0))
        q = recalfit.transform(p, a)
        # the ratio identity — this is the proof
        for i in matchboard.OUTCOMES:
            for j in matchboard.OUTCOMES:
                assert q[i] / q[j] == pytest.approx((p[i] / p[j]) ** a,
                                                    rel=1e-11)
        # ...and therefore the ranking is the same ranking
        assert (sorted(matchboard.OUTCOMES, key=lambda k: p[k])
                == sorted(matchboard.OUTCOMES, key=lambda k: q[k]))


def test_the_arsenal_coventry_control_is_the_pre_stated_vector():
    """A8 item 3, asserted at 1e-12 on the PUBLISHED marginals.

    The entry pre-states this vector before any code existed. It is the one
    control in this file that ties the implementation to a number written down
    in advance by somebody who could not see it.
    """
    q = recalfit.transform(ARSENAL_COVENTRY, recalfit.A)
    for k in matchboard.OUTCOMES:
        assert q[k] == pytest.approx(ARSENAL_COVENTRY_RECAL[k], abs=1e-12), k
    assert abs(sum(q.values()) - 1.0) <= 1e-15

    # ...and the two scores A8 states beside it, for a 3–0 home win
    assert recalfit.rps(ARSENAL_COVENTRY, "home") == \
        pytest.approx(0.030635566250, abs=1e-12)
    assert recalfit.rps(q, "home") == pytest.approx(0.039812583664, abs=1e-12)
    # A8 records the sign deliberately: on THIS fixture the transform scored
    # WORSE, and the entry pre-states no expectation about the sign of any live
    # difference.
    assert recalfit.rps(q, "home") - recalfit.rps(ARSENAL_COVENTRY, "home") == \
        pytest.approx(+0.009177017414, abs=1e-12)


def test_a_four_decimal_control_cannot_tell_the_two_inputs_apart():
    """A8 item 4 — the rounding trap, as an executable measurement.

    The rendered triple and the published one transform to DIFFERENT vectors
    that render the same at 4dp. A control written against the rendering would
    pass on the wrong input, which is why every control here is 1e-9 or better
    and reads the file's own probabilities.
    """
    rendered = {"home": 0.7639, "draw": 0.1618, "away": 0.0743}
    q_rendered = recalfit.transform(rendered, recalfit.A)
    q_published = recalfit.transform(ARSENAL_COVENTRY, recalfit.A)

    # identical at four decimals...
    assert ([f"{q_rendered[k]:.4f}" for k in matchboard.OUTCOMES]
            == [f"{q_published[k]:.4f}" for k in matchboard.OUTCOMES]
            == ["0.7321", "0.1793", "0.0886"])
    # ...and different at the sixth, which is the whole point
    assert q_rendered["home"] == pytest.approx(0.732102678534, abs=1e-12)
    assert q_rendered["draw"] == pytest.approx(0.179324238981, abs=1e-12)
    assert q_rendered["away"] == pytest.approx(0.088573082485, abs=1e-12)
    gaps = [abs(q_rendered[k] - q_published[k]) for k in matchboard.OUTCOMES]
    assert max(gaps) > 1e-9 and max(gaps) < 1e-4


# ==========================================================================
# 2. the objective — this project's own literal, vectorised
# ==========================================================================

def test_the_vectorised_objective_is_the_projects_own_rps_literal():
    """A8 (b) pins the objective to `epl/matchboard.py:674`, so the fit's
    vectorised form is held against that function row by row rather than
    written beside it and assumed equal.

    A second implementation of a score is exactly how two surfaces end up
    publishing different numbers under one name.
    """
    rng = np.random.default_rng(4)
    probs = rng.dirichlet((0.7, 0.7, 0.7), size=250)
    y = rng.integers(0, 3, size=250)

    vectorised = recalfit.rps_rows(probs, y)
    for i in range(probs.shape[0]):
        row = dict(zip(matchboard.OUTCOMES, probs[i]))
        assert vectorised[i] == pytest.approx(
            matchboard.rps(row, matchboard.OUTCOMES[y[i]]), abs=1e-15), i
    assert recalfit.mean_rps(probs, y) == pytest.approx(
        float(np.mean(vectorised)), abs=1e-15)


def test_the_uniform_baseline_is_the_two_literals_A7_already_carries():
    """A8 (c): exactly 5/18 for a home or away result and 1/9 for a draw — the
    same two values `epl/matchboard.py:162` carries, reached from `(1/3, 1/3,
    1/3)` rather than written down twice."""
    third = {k: 1 / 3 for k in matchboard.OUTCOMES}
    assert recalfit.rps(third, "home") == pytest.approx(5 / 18, abs=1e-15)
    assert recalfit.rps(third, "away") == pytest.approx(5 / 18, abs=1e-15)
    assert recalfit.rps(third, "draw") == pytest.approx(1 / 9, abs=1e-15)
    assert matchboard.UNIFORM_RPS == {"home": 5 / 18, "draw": 1 / 9,
                                      "away": 5 / 18}


# ==========================================================================
# 3. the corpus, by digest — checked BEFORE any fit
# ==========================================================================

def _synthetic_corpus(tmp_path, *, a_true=0.8, n=600, seed=11,
                      name="corpus.parquet") -> Path:
    """A corpus with a KNOWN answer: outcomes drawn from `p ** a_true`.

    The fit's job is to recover `a_true` from data generated under it, and a
    synthetic corpus is the only place that can be checked — the pinned one has
    whatever exponent it has.
    """
    rng = np.random.default_rng(seed)
    p = rng.dirichlet((1.2, 1.0, 1.1), size=n)
    truth = p ** a_true
    truth = truth / truth.sum(axis=1, keepdims=True)
    y = np.array([rng.choice(3, p=row) for row in truth])
    frame = pd.DataFrame({
        "dc_home": p[:, 0], "dc_draw": p[:, 1], "dc_away": p[:, 2],
        "y": y,
        "season": np.repeat(["2019/20", "2020/21", "2021/22"], n // 3),
        "date": pd.to_datetime("2020-01-01") + pd.to_timedelta(
            np.arange(n), unit="D"),
        "block": np.repeat(["b1", "b2", "b3"], n // 3),
    })
    path = tmp_path / name
    frame.to_parquet(path)
    return path


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_a_missing_corpus_is_a_typed_refusal_and_never_a_skip(tmp_path):
    """A8 (d) step 1: *a verification that quietly declines to verify is worse
    than one that was never run, because it prints something.*"""
    with pytest.raises(recalfit.CorpusMissing) as exc:
        recalfit.fit_a(tmp_path / "nothing.parquet", expect_sha256="00" * 32)
    assert "nothing.parquet" in str(exc.value)
    assert issubclass(recalfit.CorpusMissing, recalfit.RecalError)


def test_a_corpus_whose_digest_differs_is_refused_before_any_fit(tmp_path):
    """The digest is the corpus's identity. A file with the right name and the
    wrong bytes fits perfectly well and answers a different question."""
    path = _synthetic_corpus(tmp_path)
    with pytest.raises(recalfit.CorpusDigestMismatch) as exc:
        recalfit.fit_a(path, expect_sha256="00" * 32)
    # BOTH digests are printed, per A8 (d)
    assert "00" * 32 in str(exc.value) and _sha256(path) in str(exc.value)


def test_the_fit_recovers_a_planted_exponent_and_is_deterministic(tmp_path):
    """Two properties in one corpus, because they are the same claim twice.

    The procedure is a root-find of the analytic derivative, so it is a
    function of the bytes: two fits of one file return the SAME double, and
    five brackets return the same double as each other. And on data generated
    under a known exponent it lands near it — the fit is measuring what it
    says it measures rather than converging on an artefact.
    """
    path = _synthetic_corpus(tmp_path, a_true=0.8, n=900)
    digest = _sha256(path)

    first = recalfit.fit_a(path, expect_sha256=digest)
    second = recalfit.fit_a(path, expect_sha256=digest)
    assert first["a"] == second["a"]                       # the same double
    assert first["mean_rps"] == second["mean_rps"]
    assert first["sha256"] == digest and first["n_rows"] == 900

    # ACROSS BRACKETS the agreement is measured, not assumed. A8 records that
    # five brackets return the identical double ON THE PINNED CORPUS, and that
    # is a measurement of that corpus rather than a property of `brentq`: on
    # this synthetic one, `(0.6, 0.99)` lands ONE ulp from `(0.5, 2.0)`. The
    # exact-identity claim is asserted where A8 measured it (below, guarded on
    # the parquet), and here the claim is the one that is true generally.
    for bracket in ((0.1, 3.0), (0.5, 1.5), (0.6, 0.99), (0.0001, 5.0)):
        assert recalfit.fit_a(path, expect_sha256=digest,
                              bracket=bracket)["a"] == pytest.approx(
                                  first["a"], abs=1e-12), bracket

    # the planted exponent, to the resolution 900 rows can carry
    assert first["a"] == pytest.approx(0.8, abs=0.15)
    # ...and the fit is a minimum of the pinned objective, not merely a root
    for step in (1e-3, 1e-2, 5e-2):
        assert recalfit.mean_rps_at(path, first["a"] + step,
                                    expect_sha256=digest) > first["mean_rps"]
        assert recalfit.mean_rps_at(path, first["a"] - step,
                                    expect_sha256=digest) > first["mean_rps"]


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not present")
def test_the_pinned_corpus_is_the_one_A8_froze():
    """A8 item 1: 2,280 rows, six seasons 2019/20–2024/25 at 380 each, `y`
    counts 993 / 525 / 762 — and the digest that identifies all of it."""
    assert _sha256(PINNED_CORPUS) == recalfit.CORPUS_SHA256
    frame = pd.read_parquet(PINNED_CORPUS)
    assert len(frame) == recalfit.CORPUS_ROWS == 2280
    assert frame["season"].value_counts().to_dict() == {
        s: 380 for s in recalfit.CORPUS_SEASONS}
    assert tuple(frame["y"].value_counts().sort_index()) == \
        recalfit.CORPUS_Y_COUNTS == (993, 525, 762)


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not present")
def test_the_pinned_corpus_reproduces_the_root_and_the_frozen_constant():
    """A8's own arithmetic, re-run: the root is `0.9063507710098762` from five
    brackets, the frozen literal sits `+2.66e-08` above it, and BOTH give mean
    RPS `0.20167260332083187` — the same double, to the last bit.

    That last equality is not decoration. It is why A8 (d)'s leg 2 can be an
    exact ulp comparison and leg 1 cannot be an equality.
    """
    fit = recalfit.fit_a(PINNED_CORPUS)
    assert fit["a"] == 0.9063507710098762
    # A8 (b): five different brackets, the IDENTICAL double, 7 to 12 iterations
    for bracket in ((0.5, 2.0), (0.1, 3.0), (0.5, 1.5), (0.8, 1.0),
                    (0.0001, 5.0)):
        assert recalfit.fit_a(PINNED_CORPUS, bracket=bracket)["a"] == \
            0.9063507710098762, bracket
    assert recalfit.A - fit["a"] == pytest.approx(2.65881238137311e-08,
                                                  rel=1e-9)
    assert fit["mean_rps"] == 0.20167260332083187
    assert fit["mean_rps_at_one"] == 0.20194241064214688
    assert recalfit.mean_rps_at(PINNED_CORPUS, recalfit.A) == fit["mean_rps"]
    # the reciprocal is recorded to the precision it is written at
    assert abs(1 / recalfit.A - recalfit.T) < 1e-12


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not present")
def test_the_leave_one_season_out_table_reproduces():
    """A8 (b): six LOSO refits spanning `5.707e-02`, which is the measurement
    that says the corpus resolves `a` to about ±0.03 — and therefore that ten
    of the twelve recorded decimals are bookkeeping and not information."""
    table = recalfit.loso(PINNED_CORPUS)
    assert [row["season"] for row in table] == list(recalfit.CORPUS_SEASONS)
    expected = [0.9095328926808198, 0.9310986807857933, 0.8936709290045554,
                0.9162032153073032, 0.8740293537351703, 0.9124201196131918]
    assert [row["a"] for row in table] == expected
    span = max(expected) - min(expected)
    assert span == pytest.approx(5.707e-02, abs=1e-5)
    # four of six seasons improved — two short of six, and A8 says so
    assert sum(1 for row in table if row["mean_rps_gain"] > 0) == 4


# ==========================================================================
# 4. the two verification legs (A8 (d) step 2)
# ==========================================================================

def test_leg_one_refuses_a_constant_the_corpus_does_not_produce(tmp_path):
    """A8 (d) leg 1: `|a_ledger - a_refit| <= 1e-6`, else `RefitOutOfBounds`.

    The window is fixed from curvature and from the corpus's own resolution,
    NOT from the observed gap — so it admits any faithful implementation and
    refuses a different corpus, a different transform class, or a bug.
    """
    path = _synthetic_corpus(tmp_path, a_true=0.85, n=900)
    digest = _sha256(path)
    refit = recalfit.fit_a(path, expect_sha256=digest)["a"]

    ok = recalfit.verify_fit(path, a_ledger=refit, expect_sha256=digest)
    assert ok["gap"] == 0.0 and ok["a_refit"] == refit

    with pytest.raises(recalfit.RefitOutOfBounds) as exc:
        recalfit.verify_fit(path, a_ledger=refit + 1e-3, expect_sha256=digest)
    assert repr(refit) in str(exc.value)
    assert "1e-06" in str(exc.value) or "1e-6" in str(exc.value)


def test_leg_two_sees_what_leg_one_provably_cannot(tmp_path):
    """A8 (d) leg 2, and the whole reason one objective is pinned.

    A constant INSIDE the parameter window can still be the argmin of a
    different objective. Here the constant sits `9e-7` from the re-fit — well
    inside leg 1's `1e-6` — and the pinned objective is worse there by hundreds
    of units in the last place, so leg 2 refuses what leg 1 admits.
    """
    path = _synthetic_corpus(tmp_path, a_true=0.85, n=900)
    digest = _sha256(path)
    refit = recalfit.fit_a(path, expect_sha256=digest)["a"]
    inside = refit + 9e-7
    assert abs(inside - refit) < recalfit.PARAM_TOLERANCE   # leg 1 admits it

    with pytest.raises(recalfit.ObjectiveInferior) as exc:
        recalfit.verify_fit(path, a_ledger=inside, expect_sha256=digest)
    assert "one unit in the last place" in str(exc.value)

    # ...and one ulp of slack really is one ulp: the re-fit itself passes, and
    # so does a value whose objective is identical to the last bit.
    report = recalfit.verify_fit(path, a_ledger=refit, expect_sha256=digest)
    assert report["mean_rps_at_ledger"] == report["mean_rps_at_refit"]


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not present")
def test_the_frozen_constant_passes_both_legs_on_the_pinned_corpus():
    """The positive control for the whole verification: A8's literal, on A8's
    corpus, passes leg 1 by `2.66e-08` and leg 2 WITH EQUALITY."""
    report = recalfit.verify_fit(PINNED_CORPUS)
    assert report["a_ledger"] == recalfit.A
    assert report["a_refit"] == 0.9063507710098762
    assert abs(report["gap"]) < recalfit.PARAM_TOLERANCE
    assert report["mean_rps_at_ledger"] == report["mean_rps_at_refit"] \
        == 0.20167260332083187
    assert report["sha256"] == recalfit.CORPUS_SHA256


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not present")
def test_the_nll_fitted_constant_is_invisible_to_leg_one_and_fails_leg_two():
    """A8 (b)'s asymmetry, executed on the corpus that measured it.

    Fitting the same closed class by NLL instead of RPS gives
    `0.9063511680814477` — `3.97e-07` from the RPS root, so INSIDE any
    parameter window loose enough to admit an honest re-fit, and 184 ulps worse
    on the pinned objective. This is the concrete reason one objective is
    pinned and the reason leg 2 exists.
    """
    a_nll = 0.9063511680814477
    root = 0.9063507710098762
    assert abs(a_nll - root) < recalfit.PARAM_TOLERANCE     # leg 1 cannot see it

    with pytest.raises(recalfit.ObjectiveInferior) as exc:
        recalfit.verify_fit(PINNED_CORPUS, a_ledger=a_nll)
    assert "0.20167260332083" in str(exc.value)

    # 184 ulps, counted rather than asserted from memory
    at_root = recalfit.mean_rps_at(PINNED_CORPUS, root)
    at_nll = recalfit.mean_rps_at(PINNED_CORPUS, a_nll)
    ulps, walk = 0, at_root
    while walk < at_nll and ulps < 10_000:
        walk = np.nextafter(walk, np.inf)
        ulps += 1
    assert ulps == 184


# ==========================================================================
# 5. the grounding artifacts — the numbers exist as files, not as prose
# ==========================================================================

GROUNDING_JSON = Path("reports/epl_recal_grounding.json")
GROUNDING_MD = Path("reports/epl_recal_grounding.md")


def test_the_grounding_json_carries_the_numbers_the_rule_stands_on():
    """A design document is not a measurement. The constant, the corpus that
    produced it, the LOSO table and the validation figures are written to a
    tracked file so a later reader can read them without re-running anything —
    and without taking the amendment ledger's prose on trust.

    CI-safe by construction: this reads the COMMITTED artifact, not the corpus.
    """
    doc = json.loads(GROUNDING_JSON.read_text())
    assert doc["a"] == recalfit.A == 0.906350797598
    assert doc["T"] == recalfit.T
    assert doc["rule_version"] == recalfit.RULE_VERSION == "dc-1x2-recal-1"
    assert doc["arm"] == "dc_1x2_recal"
    assert doc["corpus"]["sha256"] == recalfit.CORPUS_SHA256
    assert doc["corpus"]["n_rows"] == 2280
    assert doc["corpus"]["y_counts"] == [993, 525, 762]
    assert doc["corpus"]["seasons"] == list(recalfit.CORPUS_SEASONS)

    # the fit, and the honest statement of what the constant is
    assert doc["fit"]["root"] == 0.9063507710098762
    assert doc["fit"]["literal_minus_root"] == pytest.approx(2.66e-08, rel=1e-2)
    assert doc["fit"]["mean_rps_at_literal"] == 0.20167260332083187
    assert doc["fit"]["mean_rps_at_root"] == 0.20167260332083187
    assert doc["fit"]["mean_rps_at_one"] == 0.20194241064214688

    # six LOSO refits, and the span that says the corpus resolves `a` to ±0.03
    assert [row["season"] for row in doc["loso"]] == list(recalfit.CORPUS_SEASONS)
    assert doc["loso_span"] == pytest.approx(5.707e-02, abs=1e-5)

    # the validation figures A8 (e) QUOTES, marked as quoted
    quoted = doc["validation_quoted"]
    assert quoted["loso_ci_95"] == [-0.000353, 0.000646]
    assert quoted["forward_2025_26_mean_rps_difference"] == 0.000667
    assert quoted["weekly_refit_mean_rps_difference"] == -0.0000056
    assert doc["rejected_variants"] == list(recalfit.REJECTED_VARIANTS)


def test_the_grounding_report_obeys_the_language_rule():
    """A8 (e) is binding on every surface, and this is a surface.

    A language rule nothing checks is a language rule that survives exactly as
    long as nobody is in a hurry.
    """
    text = GROUNDING_MD.read_text()
    assert recalfit.CHALLENGER_PHRASE in text
    assert recalfit.PUBLISHED_LAW_PHRASE in text
    for banned in recalfit.FORBIDDEN_PHRASES:
        assert banned not in text.lower(), banned
    # both intervals cross zero, and that is the finding rather than a footnote
    assert "cross" in text.lower() and "zero" in text.lower()
    # the rejected variants are named so nobody re-proposes one as a new idea
    for name in ("Platt", "vector scaling", "affine"):
        assert name in text, name
    # A7 (f)'s narrowing, carried onto this surface too. WORD BOUNDARIES, not
    # substrings: "bet" is inside "better" and "between", and a check that
    # honest prose cannot satisfy is a check somebody deletes.
    for forbidden in (r"\bodds\b", r"\bstake[sd]?\b", r"\bbets?\b",
                      r"\bbetting\b", r"\bpayout\b", r"\bprofit\b",
                      r"\bboth teams\b", r"\bcorrect score\b",
                      r"\bover/under\b", r"\btotal goals\b",
                      r"\bbenchmark\b"):
        assert re.search(forbidden, text.lower()) is None, forbidden


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not present")
def test_the_committed_grounding_is_what_the_corpus_produces_today(tmp_path):
    """The artifact is a PURE FUNCTION of the corpus and this module — no
    clock, no environment, nothing that drifts — so regenerating it must
    reproduce the committed bytes.

    A grounding file that cannot be regenerated is a number somebody wrote
    down, which is the thing A8 (b) exists to stop.
    """
    json_path, md_path = recalfit.write_grounding(
        tmp_path / "g.json", tmp_path / "g.md", corpus=PINNED_CORPUS)
    assert json_path.read_bytes() == GROUNDING_JSON.read_bytes()
    assert md_path.read_bytes() == GROUNDING_MD.read_bytes()


# ==========================================================================
# 6. the shadow ledger (A8 (c)) — mechanics, on synthetic bundles
# ==========================================================================

from epl import leaguesim, recalshadow, season as season_mod   # noqa: E402

#: The preserved MW0 bundle. Present on the machine that issued it and nowhere
#: else, so every test that reads it is guarded.
COMMITTED_OPENER = Path("data/epl/sim/issuances/2026_27/2026-08-21")

#: The committed shadow ledger, once the backfill has filed into it.
SHADOW_LEDGER = Path("reports/epl_recal_shadow.jsonl")

#: A five-fixture synthetic season, in the shape `epl/tests/test_matchboard.py`
#: already uses — deliberately NOT in the order a reader would guess, because
#: `fixture_ordinal` is a RANK among the SORTED ids.
SEASON_IDS = ("2627:alpha:bravo", "2627:charlie:delta", "2627:echo:foxtrot",
              "2627:golf:hotel", "2627:india:juliet")
FACTS = {
    "2627:alpha:bravo": {"home": "alpha", "away": "bravo", "date": "2026-08-21"},
    "2627:charlie:delta": {"home": "charlie", "away": "delta",
                           "date": "2026-08-22"},
    "2627:echo:foxtrot": {"home": "echo", "away": "foxtrot",
                          "date": "2026-08-23"},
    "2627:golf:hotel": {"home": "golf", "away": "hotel", "date": "2026-08-24"},
    "2627:india:juliet": {"home": "india", "away": "juliet",
                          "date": "2026-08-25"},
}


def _arrays(scorelines, particle, ordinals) -> dict:
    return {"scorelines": np.asarray(scorelines, np.int8),
            "particle": np.asarray(particle, np.int16),
            "fixture_ordinals": np.asarray(ordinals, np.int32)}


def _spread_rows():
    """Four particles that disagree, so the marginals are not degenerate."""
    per = 250
    particle = np.repeat(np.arange(4, dtype=np.int16), per)
    scorelines = np.zeros((4 * per, 1, 2), np.int8)
    scorelines[0 * per:1 * per] = (4, 0)
    scorelines[1 * per:2 * per] = (1, 1)
    scorelines[2 * per:3 * per] = (0, 1)
    scorelines[3 * per:3 * per + per // 2] = (2, 0)
    scorelines[3 * per + per // 2:4 * per] = (0, 2)
    return _arrays(scorelines, particle, [0])


def _pair_rows():
    """The same four particles over TWO columns, so a batch has two fixtures.

    Column 1 leans away where column 0 leans home, so the two fixtures do not
    share a probability vector and a row that resolved the wrong column would
    be visible rather than coincidentally right.
    """
    per = 250
    particle = np.repeat(np.arange(4, dtype=np.int16), per)
    scorelines = np.zeros((4 * per, 2, 2), np.int8)
    scorelines[0 * per:1 * per, 0] = (4, 0)
    scorelines[1 * per:2 * per, 0] = (1, 1)
    scorelines[2 * per:3 * per, 0] = (0, 1)
    scorelines[3 * per:3 * per + per // 2, 0] = (2, 0)
    scorelines[3 * per + per // 2:4 * per, 0] = (0, 2)
    scorelines[0 * per:1 * per, 1] = (0, 3)
    scorelines[1 * per:2 * per, 1] = (0, 1)
    scorelines[2 * per:3 * per, 1] = (2, 2)
    scorelines[3 * per:4 * per, 1] = (1, 0)
    return _arrays(scorelines, particle, [0, 1])


def _board(rows=None, **overrides) -> dict:
    rows = matchboard.derive_rows(_spread_rows(), fixture_ids=SEASON_IDS,
                                  facts=FACTS) if rows is None else rows
    doc = {
        "schema_version": matchboard.SCHEMA_VERSION,
        "season": "2026/27", "arm": "dc_native",
        "cutoff": "2026-08-21 00:00:00", "observed_by": "2026-08-21 00:00:00",
        "seed": 20260611, "chunk_size": 2000, "n_sims": int(rows[0]["n_sims"]),
        "n_particles": int(rows[0]["n_particles"]), "n_fixtures": len(rows),
        "source_rows": "rows_dc_native.npz",
        "effective_posterior_hash": "b8" * 32, "run_digest": "3a" * 32,
        "manifest_sha256": "01" * 32, "fixtures_base_sha256": "02" * 32,
        "kickoff_amendments_sha256": "03" * 32,
        "max_goals": 10, "n_provisional": 38, "rows_provenance": "reproduction",
        "source_bundle": "data/epl/sim/issuances/2026_27/2026-08-21",
        "rows": rows,
    }
    doc.update(overrides)
    return doc


def _ledger(*rows):
    """A results ledger for the synthetic season, resolved by SEASON'S OWN code.

    :func:`epl.season.resolve_ledger` is the one implementation of this
    project's bitemporal resolution, so a shadow row built against this view is
    built against the same conflict rules and not against a second set.
    """
    return season_mod.resolve_ledger(
        [{"observed_at": "2026-08-22T09:00:00",
          "date_played": FACTS[row["fixture_id"]]["date"], **row}
         for row in rows],
        identify=lambda row: str(row["fixture_id"]))


def _played(fixture_id="2627:alpha:bravo", hg=2, ag=0, **extra):
    return {"fixture_id": fixture_id, "hg": hg, "ag": ag, **extra}


def _result(fixture_id="2627:alpha:bravo", hg=2, ag=0, mw=1,
            ingest="manual/test"):
    return {"fixture_id": fixture_id, "home_goals": hg, "away_goals": ag,
            "matchweek": mw, "ingest": ingest}


def _one_row(board=None, **kw):
    board = _board() if board is None else board
    return recalshadow.score(board, [_result(**kw)],
                             ledger=_ledger(_played(hg=kw.get("hg", 2),
                                                    ag=kw.get("ag", 0))))[0]


def test_a_shadow_row_carries_every_field_A8_names_and_nothing_else():
    """A8 (c)'s table, as the row schema — self-contained by construction.

    ``schema_version`` is on the ROW and not only on the file: A8 (c) states
    the ledger's schema is `epl-recal-shadow-1`, a JSONL file has no header to
    put it in, and the same ruling requires every row to be checkable without
    opening anything else.
    """
    row = _one_row()
    assert tuple(row) == recalshadow.ROW_FIELDS
    assert row["schema_version"] == recalshadow.SCHEMA_VERSION \
        == "epl-recal-shadow-1"
    assert row["arm"] == recalfit.ARM == "dc_1x2_recal"
    assert row["rule_version"] == recalfit.RULE_VERSION == "dc-1x2-recal-1"
    assert row["a"] == recalfit.A
    assert row["corpus_sha256"] == recalfit.CORPUS_SHA256
    # A7 (f), carried onto this surface in full: no benchmark comparison column
    assert not any("benchmark" in k for k in row)


def test_probs_raw_is_the_published_marginal_copied_and_never_re_priced():
    """A8 (c): ``probs_raw`` is the matchboard's own object.

    This is what makes A8 item 6 an IDENTITY rather than an approximation: a
    shadow layer that re-simulated, re-aggregated or even re-rounded the
    marginals would produce a number that is nearly the published one, and
    "nearly" is not what the entry pre-states.
    """
    board = _board()
    row = _one_row(board)
    published = board["rows"][0]["probs"]
    assert row["probs_raw"] == published
    for k in matchboard.OUTCOMES:
        assert row["probs_raw"][k] == published[k]          # the same double
    # ...and probs_recal is that object through the frozen transform
    assert row["probs_recal"] == recalfit.transform(published, recalfit.A)
    assert abs(sum(row["probs_recal"].values()) - 1.0) <= 1e-9


def test_rps_raw_is_the_same_number_the_A7_scorecard_publishes():
    """A8 item 6, as a mechanism rather than as a coincidence.

    The A7 scorecard's ``rps`` and this ledger's ``rps_raw`` score the SAME
    probabilities against the SAME outcome through the SAME literal, so the two
    are the same double. Asserted here on a synthetic bundle so CI can run it;
    the live control is the ten MW1 fixtures.
    """
    board = _board()
    ledger = _ledger(_played(hg=2, ag=0))
    scorecard = matchboard.score(board, [_result()], ledger=ledger)[0]
    shadow = recalshadow.score(board, [_result()], ledger=ledger)[0]
    assert shadow["rps_raw"] == scorecard["rps"]            # the same double
    assert shadow["rps_uniform"] == scorecard["rps_uniform"]
    assert shadow["outcome"] == scorecard["outcome"] == "home"
    assert shadow["matchweek"] == 1 and shadow["ingest"] == "manual/test"


def test_the_identity_survives_marginals_that_are_not_round_decimals():
    """The identity above, on a vector a rounding could actually move.

    THE FIRST VERSION OF THIS TEST DID NOT BIND, and the mutation that proved
    it is worth recording: replacing the copy with
    ``round(float(v), 6)`` left the whole file green. A simulated marginal is
    ``count / n_sims`` — a coarse rational, exact at six decimals for any run
    this project produces — so a six-place rounding of one is the identity map
    and a test built on one cannot tell a copy from a re-pricing.

    So the control is a vector with digits all the way down. Any re-pricing,
    re-normalising or re-rounding of `probs_raw` moves `rps_raw` off the
    matchboard's `rps`, and both are compared as doubles.
    """
    board = _board()
    awkward = {"home": 0.7638996123456789, "draw": 0.1617501234567891,
               "away": 0.0743502642 - 5.55e-17}
    board["rows"] = [dict(board["rows"][0], probs=awkward)]
    total = sum(awkward.values())
    assert total != 1.0 and abs(total - 1.0) < 1e-9, "an honest raw marginal"

    ledger = _ledger(_played(hg=2, ag=0))
    scorecard = matchboard.score(board, [_result()], ledger=ledger)[0]
    shadow = recalshadow.score(board, [_result()], ledger=ledger)[0]
    assert shadow["probs_raw"] == awkward                   # the same doubles
    assert shadow["rps_raw"] == scorecard["rps"]            # the same double
    # ...and the recalibrated vector renormalises EXACTLY, whatever the raw
    # cells summed to: the denominator is the sum of the transformed cells and
    # never an assumption that the input summed to one.
    assert abs(sum(shadow["probs_recal"].values()) - 1.0) <= 1e-15


def test_the_uniform_column_is_the_two_pre_stated_literals():
    """A8 (c): exactly 5/18 for a home or away result, 1/9 for a draw."""
    board = _board()
    home = recalshadow.score(board, [_result(hg=2, ag=0)],
                             ledger=_ledger(_played(hg=2, ag=0)))[0]
    draw = recalshadow.score(board, [_result(hg=1, ag=1)],
                             ledger=_ledger(_played(hg=1, ag=1)))[0]
    away = recalshadow.score(board, [_result(hg=0, ag=2)],
                             ledger=_ledger(_played(hg=0, ag=2)))[0]
    assert home["rps_uniform"] == pytest.approx(5 / 18, abs=1e-15)
    assert away["rps_uniform"] == pytest.approx(5 / 18, abs=1e-15)
    assert draw["rps_uniform"] == pytest.approx(1 / 9, abs=1e-15)
    assert (home["outcome"], draw["outcome"], away["outcome"]) == \
        ("home", "draw", "away")


def test_a_forecast_that_did_not_precede_the_kickoff_is_refused_by_name():
    """A8 (c) restating A7 (e): REFUSED, naming the fixture and the stamp —
    never dropped. In an append-only file a silent omission is invisible."""
    board = _board()
    view = _ledger(_played(hg=1, ag=0))
    for field in ("cutoff", "observed_by"):
        late = dict(board, **{field: "2026-08-25 00:00:00"})
        with pytest.raises(recalshadow.RowInadmissible) as exc:
            recalshadow.score(late, [_result(hg=1, ag=0)], ledger=view)
        assert "2627:alpha:bravo" in str(exc.value)
        assert field in str(exc.value)
        assert "2026-08-25" in str(exc.value)               # the stamp itself
        assert issubclass(recalshadow.RowInadmissible, recalfit.RecalError)
    # POSITIVE CONTROL: on the day the season had the kickoff it is admissible
    assert recalshadow.score(board, [_result(hg=1, ag=0)],
                             ledger=view)[0]["date"] == "2026-08-21"


def test_the_season_ledger_is_the_only_door_a_result_comes_through():
    """A8 (c): results resolve through `epl.season` and a results file is a
    REQUEST to score rows the ledger already carries.

    The conflict rules are NOT re-implemented here — this delegates to
    `matchboard.score`, which is the one place they live — so the proof is that
    the same three refusals still fire on this surface.
    """
    board = _board()
    # 1. a fixture the ledger resolves no result for
    with pytest.raises(matchboard.MatchboardError) as exc:
        recalshadow.score(board, [_result()], ledger=_ledger())
    assert "results ledger resolves no result" in str(exc.value)
    # 2. a scoreline that disagrees with the one the ledger resolved
    with pytest.raises(matchboard.MatchboardError) as exc:
        recalshadow.score(board, [_result(hg=9, ag=0)],
                          ledger=_ledger(_played(hg=2, ag=0)))
    assert "source of truth" in str(exc.value)
    # 3. a goal count that is not one, through `epl.season.goal_count`
    with pytest.raises(matchboard.MatchboardError):
        recalshadow.score(board, [_result(hg=-7, ag=0)],
                          ledger=_ledger(_played(hg=-7, ag=0)))


def test_the_same_row_filed_twice_is_a_no_op(tmp_path):
    """A8 (c): idempotent by `(fixture_id, run_digest)`. The operator runs this
    weekly, by hand, so a re-run must not double every row."""
    path = tmp_path / "shadow.jsonl"
    rows = recalshadow.score(_board(), [_result()],
                             ledger=_ledger(_played(hg=2, ag=0)))
    assert recalshadow.append_shadow(path, rows) == {"appended": 1,
                                                     "repeated": 0}
    first = path.read_bytes()
    assert recalshadow.append_shadow(path, rows) == {"appended": 0,
                                                     "repeated": 1}
    assert path.read_bytes() == first                       # byte for byte


def test_a_disagreeing_re_file_is_refused_naming_both_rows(tmp_path):
    """An append-only ledger holding two different rows for one key is worse
    than one that refused the second: nothing downstream can say which of them
    the record means."""
    path = tmp_path / "shadow.jsonl"
    rows = recalshadow.score(_board(), [_result()],
                             ledger=_ledger(_played(hg=2, ag=0)))
    recalshadow.append_shadow(path, rows)
    changed = [dict(rows[0], ingest="manual/somewhere-else")]
    with pytest.raises(recalshadow.RowConflict) as exc:
        recalshadow.append_shadow(path, changed)
    assert "manual/test" in str(exc.value)                  # the row on file
    assert "manual/somewhere-else" in str(exc.value)        # the row offered
    assert path.read_bytes().count(b"\n") == 1              # nothing appended


def test_nothing_is_written_unless_every_row_in_the_batch_passes(tmp_path):
    """A8 (c): *nothing is written unless every row passes.* A batch with one
    bad row appends none of them, so a re-run after the fix is a clean run and
    not a partial repair."""
    path = tmp_path / "shadow.jsonl"
    board = _board(matchboard.derive_rows(_pair_rows(), fixture_ids=SEASON_IDS,
                                          facts=FACTS))
    view = _ledger(_played(hg=2, ag=0),
                   _played("2627:charlie:delta", hg=0, ag=1))
    good = recalshadow.score(board, [_result()], ledger=view)
    recalshadow.append_shadow(path, good)

    other = recalshadow.score(
        board, [_result("2627:charlie:delta", hg=0, ag=1)], ledger=view)
    batch = other + [dict(good[0], ingest="disagrees")]
    with pytest.raises(recalshadow.RowConflict):
        recalshadow.append_shadow(path, batch)
    assert len(recalshadow.read_shadow(path)) == 1          # the good one only


def test_a_bundle_the_matchboard_cannot_be_derived_from_is_refused(tmp_path):
    """A8 (c): `probs_raw` is the published matchboard's own object, so a
    source that has no matchboard is refused rather than priced here."""
    bundle = tmp_path / "2026-08-21"
    bundle.mkdir()
    (bundle / "issuance.json").write_text(json.dumps(
        {"season": "2026/27", "cutoff": "2026-08-21 00:00:00",
         "observed_by": "2026-08-21 00:00:00",
         "arms": ["dc_wdl_bridge"], "digests": {}}))
    with pytest.raises(matchboard.MatchboardError) as exc:
        recalshadow.board_from(bundle)
    assert "dc_native" in str(exc.value)


# ==========================================================================
# 7. verify() — the row legs (A8 (d) steps 3, 4, 5)
# ==========================================================================

def _filed(tmp_path, rows) -> Path:
    path = tmp_path / "shadow.jsonl"
    path.write_text("".join(leaguesim.canonical_json(r) + "\n" for r in rows))
    return path


def _corpus_and_rows(tmp_path):
    """A synthetic corpus with its own digest, and one row fitted under it.

    The corpus is synthetic so CI can run the whole verification; the row's
    frozen-rule fields name that corpus, which is what step 4 checks.
    """
    corpus = _synthetic_corpus(tmp_path, a_true=0.85, n=900)
    digest = _sha256(corpus)
    a = recalfit.fit_a(corpus, expect_sha256=digest)["a"]
    rows = recalshadow.score(_board(), [_result()],
                             ledger=_ledger(_played(hg=2, ag=0)),
                             a=a, corpus_sha256=digest)
    return corpus, digest, rows


def test_verify_passes_a_ledger_that_re_derives(tmp_path):
    """The positive control: the whole command, on a corpus and rows that
    agree. Without it every refusal below could be a refusal of everything."""
    corpus, digest, rows = _corpus_and_rows(tmp_path)
    report = recalshadow.verify(_filed(tmp_path, rows), corpus=corpus,
                                a_ledger=rows[0]["a"], expect_sha256=digest)
    assert report["n_rows"] == 1
    assert report["fit"]["a_refit"] == rows[0]["a"]
    assert report["fit"]["sha256"] == digest


def test_verify_re_derives_probs_recal_and_refuses_a_hand_edited_cell(tmp_path):
    """A8 (d) step 3 — THE EXACT LEG, held at 1e-12.

    This comparison needs no optimiser and no corpus; it is arithmetic on the
    row's own inputs, which is exactly why it is the one leg held twelve orders
    below the parameter's.
    """
    corpus, digest, rows = _corpus_and_rows(tmp_path)
    # a nudge far below anything a reader would see, and far above 1e-12
    bent = dict(rows[0])
    bent["probs_recal"] = dict(bent["probs_recal"])
    bent["probs_recal"]["draw"] += 1e-9
    with pytest.raises(recalshadow.RecalMismatch) as exc:
        recalshadow.verify(_filed(tmp_path, [bent]), corpus=corpus,
                           a_ledger=rows[0]["a"], expect_sha256=digest)
    assert "2627:alpha:bravo" in str(exc.value) and "draw" in str(exc.value)

    # ...and a nudge BELOW the tolerance is not refused by step 3, so 1e-12 is
    # the line and not exactness. `rps_recal` is recomputed from the nudged
    # vector: step 5 scores the row's own probabilities EXACTLY, and leaving a
    # stale score beside a moved vector would be a different defect failing a
    # different leg.
    ok = dict(rows[0])
    ok["probs_recal"] = dict(ok["probs_recal"])
    ok["probs_recal"]["draw"] += 1e-14
    ok["rps_recal"] = recalfit.rps(ok["probs_recal"], ok["outcome"])
    recalshadow.verify(_filed(tmp_path, [ok]), corpus=corpus,
                       a_ledger=rows[0]["a"], expect_sha256=digest)


def test_verify_refuses_a_row_filed_under_another_rules_name(tmp_path):
    """A8 (d) step 4: a row fitted under one rule and filed under another's
    name is the failure this catches."""
    corpus, digest, rows = _corpus_and_rows(tmp_path)
    for field, value in (("rule_version", "dc-1x2-recal-2"),
                         ("corpus_sha256", "00" * 32),
                         ("schema_version", "epl-recal-shadow-2"),
                         ("arm", "dc_native")):
        bent = dict(rows[0], **{field: value})
        with pytest.raises(recalshadow.SchemaMismatch) as exc:
            recalshadow.verify(_filed(tmp_path, [bent]), corpus=corpus,
                               a_ledger=rows[0]["a"], expect_sha256=digest)
        assert field in str(exc.value), field
    # `a` is held to the LEDGER's constant — the one leg 1 re-fitted. The row
    # is bent INTERNALLY CONSISTENTLY, recalibrated and rescored under the
    # other constant, because that is the row step 4 exists for: one that is
    # arithmetically perfect under a rule nobody froze. A row with only its `a`
    # field changed fails step 3 first, and asserting SchemaMismatch on that
    # one would be asserting the wrong leg.
    other = rows[0]["a"] + 1e-9
    q = recalfit.transform(rows[0]["probs_raw"], other)
    bent = dict(rows[0], a=other, probs_recal=q,
                rps_recal=recalfit.rps(q, rows[0]["outcome"]))
    recalshadow.check_sums(q, fixture_id=bent["fixture_id"])   # still a vector
    with pytest.raises(recalshadow.SchemaMismatch) as exc:
        recalshadow.verify(_filed(tmp_path, [bent]), corpus=corpus,
                           a_ledger=rows[0]["a"], expect_sha256=digest)
    assert repr(rows[0]["a"]) in str(exc.value)


def test_verify_recomputes_all_three_scores_and_the_sum(tmp_path):
    """A8 (d) step 5. A recorded score that does not recompute from the row's
    own probabilities and outcome is a number nobody can check."""
    corpus, digest, rows = _corpus_and_rows(tmp_path)
    for field in ("rps_raw", "rps_recal", "rps_uniform"):
        bent = dict(rows[0], **{field: rows[0][field] + 1e-6})
        with pytest.raises(recalshadow.RecalMismatch) as exc:
            recalshadow.verify(_filed(tmp_path, [bent]), corpus=corpus,
                               a_ledger=rows[0]["a"], expect_sha256=digest)
        assert field in str(exc.value), field
    # Σq = 1 within 1e-9, which A8 item 5 pre-states on every row. It is a
    # BELT TO STEP 3'S BRACE and this test says so rather than implying the
    # check is independently load-bearing: step 3 already holds each cell to
    # 1e-12 against a transform that renormalises exactly, so three cells can
    # be off by at most 3e-12 and still pass — never the 1e-9 this would need.
    # A vector scaled far enough to break the sum breaks the re-derivation
    # first, and the refusal below is step 3's.
    bent = dict(rows[0])
    bent["probs_recal"] = {k: v * 0.9 for k, v in bent["probs_recal"].items()}
    with pytest.raises(recalshadow.RecalMismatch):
        recalshadow.verify(_filed(tmp_path, [bent]), corpus=corpus,
                           a_ledger=rows[0]["a"], expect_sha256=digest)
    # so the invariant is exercised where it CAN fire on its own: directly, on
    # a vector nothing derived.
    with pytest.raises(recalshadow.RecalMismatch) as exc:
        recalshadow.check_sums({"home": 0.4, "draw": 0.3, "away": 0.2},
                               fixture_id="2627:alpha:bravo")
    assert "2627:alpha:bravo" in str(exc.value)
    recalshadow.check_sums(rows[0]["probs_recal"],
                           fixture_id="2627:alpha:bravo")


def test_verify_refuses_an_inadmissible_row_on_the_file(tmp_path):
    """A8 (d) step 5: the A7 (e) ordering is re-checked from the row's own
    three stamps, so a row that got past `score` by another route is still
    caught by the file's own reader."""
    corpus, digest, rows = _corpus_and_rows(tmp_path)
    bent = dict(rows[0], observed_by="2026-08-25 00:00:00")
    with pytest.raises(recalshadow.RowInadmissible) as exc:
        recalshadow.verify(_filed(tmp_path, [bent]), corpus=corpus,
                           a_ledger=rows[0]["a"], expect_sha256=digest)
    assert "observed_by" in str(exc.value) and "2026-08-25" in str(exc.value)


def test_verify_refuses_two_rows_claiming_one_key(tmp_path):
    """A8 (c): one row per `(fixture_id, run_digest)`. A file that already
    holds two is refused by the reader as well as by the writer."""
    corpus, digest, rows = _corpus_and_rows(tmp_path)
    twice = [rows[0], dict(rows[0], ingest="another")]
    with pytest.raises(recalshadow.RowConflict) as exc:
        recalshadow.verify(_filed(tmp_path, twice), corpus=corpus,
                           a_ledger=rows[0]["a"], expect_sha256=digest)
    assert "2627:alpha:bravo" in str(exc.value)


def test_verify_refuses_a_missing_corpus_rather_than_skipping(tmp_path):
    """A8 (d) step 1, on the command that matters most: CI has no `data/`, the
    command refuses there, and that is its job."""
    _corpus, digest, rows = _corpus_and_rows(tmp_path)
    with pytest.raises(recalfit.CorpusMissing):
        recalshadow.verify(_filed(tmp_path, rows),
                           corpus=tmp_path / "gone.parquet",
                           a_ledger=rows[0]["a"], expect_sha256=digest)


def test_the_shadow_layer_reads_no_clock_and_moving_the_clock_proves_it(
        monkeypatch):
    """Every row is a function of the bundle, the ledger and the frozen rule.

    Not string-matched against today's date — that guard false-alarms the day a
    kickoff equals the wall clock. The clock is MOVED and the bytes must be
    identical. The swap goes through ``sys.modules`` as well as the module
    attribute, so a function-local ``import time`` is intercepted too.
    """
    import datetime as real_datetime
    import sys
    import time as real_time

    board, view = _board(), _ledger(_played(hg=2, ag=0))
    before = leaguesim.canonical_json(
        recalshadow.score(board, [_result()], ledger=view))

    class _FrozenTime:
        @staticmethod
        def time():
            return 0.0

        @staticmethod
        def monotonic():
            return 0.0

        @staticmethod
        def perf_counter():
            return 0.0

        @staticmethod
        def strftime(fmt, t=None):
            return "FROZEN"

        @staticmethod
        def gmtime(secs=None):
            return real_time.gmtime(0)

        @staticmethod
        def localtime(secs=None):
            return real_time.localtime(0)

    class _FrozenDatetime:
        timezone = real_datetime.timezone
        timedelta = real_datetime.timedelta

        class datetime(real_datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(1970, 1, 1)

            @classmethod
            def utcnow(cls):
                return cls(1970, 1, 1)

        class date(real_datetime.date):
            @classmethod
            def today(cls):
                return cls(1970, 1, 1)

    monkeypatch.setitem(sys.modules, "time", _FrozenTime)
    monkeypatch.setitem(sys.modules, "datetime", _FrozenDatetime)
    monkeypatch.setattr(recalshadow, "time", _FrozenTime, raising=False)
    monkeypatch.setattr(recalshadow, "datetime", _FrozenDatetime, raising=False)

    assert leaguesim.canonical_json(
        recalshadow.score(board, [_result()], ledger=view)) == before, (
        "a shadow row changed when the clock moved — the derivation is reading "
        "a wall clock, so the same bundle would not reproduce tomorrow")


def test_no_market_vocabulary_reaches_a_shadow_row():
    """A7 (f)'s narrowing, binding on this surface in full. WORD BOUNDARIES,
    not substrings: "bet" is inside "better", and a check honest prose cannot
    satisfy is a check somebody deletes."""
    text = leaguesim.canonical_json(_one_row()).lower()
    for forbidden in (r"\bodds\b", r"\bstake[sd]?\b", r"\bbets?\b",
                      r"\bbetting\b", r"\bpayout\b", r"\bprofit\b",
                      r"\bboth teams\b", r"\bcorrect score\b",
                      r"\bover/under\b", r"\btotal goals\b", r"\bbenchmark\b"):
        assert re.search(forbidden, text) is None, forbidden


# ==========================================================================
# 8. the command A8 pre-stated by name (A8 (d))
# ==========================================================================

from epl import recal                                        # noqa: E402


def test_the_command_is_the_one_A8_named_with_the_two_modes():
    """A8 (d) names `epl/recal.py`, invoked as `python -m epl.recal verify`.

    The rule and the ledger live in two modules because they are two subjects —
    a fit that reads a corpus, and a ledger that reads a season — but the
    OPERATOR's surface is the one the amendment wrote down, and a command
    nobody can find under the name the ledger gives it is a command that gets
    reinvented.
    """
    assert recal.__doc__
    assert recal.SHADOW_PATH == recalshadow.SHADOW_PATH
    for mode in ("verify", "score"):
        assert mode in recal.MODES


def test_a_missing_corpus_is_a_STOP_and_exit_2_not_a_traceback(tmp_path,
                                                               capsys):
    """A8 (d): CI has no `data/`, the command refuses there, and that is its
    job. It must refuse the way every typed refusal in this project refuses —
    `STOP: <TypeName>: …` and exit 2 — because a refusal an operator cannot
    tell from a crash teaches them to ignore crashes.
    """
    code = recal.main(["verify", "--ledger", str(tmp_path / "none.jsonl"),
                       "--corpus", str(tmp_path / "gone.parquet")])
    err = capsys.readouterr().err
    assert code == 2, f"exit {code}; a typed refusal exits 2, a crash exits 1"
    assert "STOP: CorpusMissing" in err
    assert "Traceback" not in err


def test_a_corpus_that_is_not_the_frozen_one_is_a_STOP_too(tmp_path, capsys):
    """The digest is the corpus's identity, and the command says both."""
    corpus = _synthetic_corpus(tmp_path)
    code = recal.main(["verify", "--ledger", str(tmp_path / "none.jsonl"),
                       "--corpus", str(corpus)])
    err = capsys.readouterr().err
    assert code == 2
    assert "STOP: CorpusDigestMismatch" in err
    assert recalfit.CORPUS_SHA256 in err and _sha256(corpus) in err


@pytest.mark.skipif(not PINNED_CORPUS.exists(),
                    reason="the pinned corpus is not present")
def test_the_command_verifies_the_committed_shadow_ledger(capsys):
    """The live control, end to end: the frozen constant re-derived from the
    pinned corpus, and every row on the committed ledger re-derived from its
    own inputs. Skip-guarded, because `data/` is not in git — and the mechanics
    above are the CI-safe half of the same checks."""
    code = recal.main(["verify"])
    out = capsys.readouterr().out
    assert code == 0
    assert recalfit.ARM in out and recalshadow.SCHEMA_VERSION in out


@pytest.mark.skipif(not SHADOW_LEDGER.exists(),
                    reason="the shadow ledger has no rows yet")
def test_the_committed_shadow_ledger_is_this_schema_and_nothing_else():
    """Whatever the backfill filed, every row on the tracked file is an A8 row.

    CI-safe by construction: this reads the COMMITTED ledger, not the corpus.
    """
    rows = recalshadow.read_shadow(SHADOW_LEDGER)
    assert rows, "the committed shadow ledger is empty"
    for row in rows:
        assert tuple(row) == recalshadow.ROW_FIELDS
        assert row["schema_version"] == recalshadow.SCHEMA_VERSION
        assert row["arm"] == recalfit.ARM
        assert row["rule_version"] == recalfit.RULE_VERSION
        assert row["a"] == recalfit.A
        assert row["corpus_sha256"] == recalfit.CORPUS_SHA256
        # the row re-derives from its own inputs, with no corpus in sight
        recalshadow.check_row(row, a_ledger=recalfit.A,
                              corpus_sha256=recalfit.CORPUS_SHA256)
    # one row per (fixture, issuance)
    keys = [recalshadow.shadow_key(row) for row in rows]
    assert len(set(keys)) == len(keys)
