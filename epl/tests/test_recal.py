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
