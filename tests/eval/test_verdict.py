"""Tests for V10's outcome resolution.

V10 scores forecasts against what happened, so a wrong outcome is not a
crash — it is a wrong verdict that still prints cleanly. These tests pin the
one thing that cannot be checked by reading the number afterwards: that the
label is the result AT 90 MINUTES, and that anything decided past 90' is
either sourced from the curated regulation table or REFUSED.

The original loader parsed a schema this repo has never had (a mapping with
``results:`` and ``match_id``/``home_score`` keys). It raised AttributeError
on the real file's top-level list, and would have settled nothing even past
that. The shootout test below is the positive control that keeps the
replacement honest.
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def verdict():
    sys.path.insert(0, str(_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "oa_verdict", _ROOT / "scripts" / "oa_verdict.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oa_verdict"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def locked_frame():
    """The real locked inventory, in the columns load_outcomes reads."""
    fixtures = yaml.safe_load(
        (_ROOT / "config" / "oa_eval_manifest.yaml").read_text())["fixtures"]
    frame = pd.DataFrame(fixtures)
    frame["date"] = frame["date"].astype(str)
    return frame


def test_every_locked_fixture_settles(verdict, locked_frame):
    """No silent drops: eligibility was frozen without outcomes, so a
    settlement gap must be impossible, not merely rare."""
    outcomes = verdict.load_outcomes(locked_frame)
    assert len(outcomes) == len(locked_frame) == 217
    assert set(outcomes.values()) <= {"home", "draw", "away"}


@pytest.mark.parametrize("home,away,date", [
    ("Argentina", "France", "2022-12-18"),     # 2-2 at 90', won on penalties
    ("Morocco", "Spain", "2022-12-06"),        # 0-0 at 90', won on penalties
])
def test_extra_time_matches_score_as_their_90_minute_draw(
        verdict, locked_frame, home, away, date):
    """The whole reason the regulation table exists. 1X2 settles at 90', so a
    shootout winner must NOT become a 'home'/'away' label — reading the final
    score here would silently score every ET match against the wrong side."""
    outcomes = verdict.load_outcomes(locked_frame)
    row = locked_frame[(locked_frame.home == home)
                       & (locked_frame.away == away)
                       & (locked_frame.date == date)]
    assert len(row) == 1, f"{home} v {away} on {date} is not in the lock"
    assert outcomes[str(row.iloc[0].fixture_id)] == "draw"


def test_a_shootout_absent_from_the_table_is_refused(
        verdict, locked_frame, tmp_path):
    """Positive control for the guard: drop a known ET fixture from the
    regulation table and the store's ET-inclusive score must be REFUSED, not
    quietly used. Without this the previous test could pass vacuously."""
    rows = yaml.safe_load(
        (_ROOT / "config" / "regulation_time_results.yaml").read_text())
    kept = [r for r in rows
            if not (str(r["date"]) == "2022-12-18" and r["home"] == "Argentina")]
    assert len(kept) == len(rows) - 1, "the fixture being dropped must exist"

    partial = tmp_path / "partial.yaml"
    partial.write_text(yaml.safe_dump(kept))
    with pytest.raises(verdict.VerdictError, match="decided past 90'"):
        verdict.load_outcomes(locked_frame, results_path=partial)


def test_p_is_the_exact_complement_of_support(verdict):
    """Spec §2.1 calls p the exact complement of the gate's support. Deriving
    it from the same bootstrap makes that an identity, so the two can never
    be reported disagreeing with each other."""
    assert verdict.p_from_support(1.0, n_boot=10000) == pytest.approx(
        1 / 10001)
    assert verdict.p_from_support(0.0, n_boot=10000) == pytest.approx(
        10001 / 10001)
    # a support that misses the 0.80 floor must carry a p above 0.20
    assert verdict.p_from_support(0.79, n_boot=10000) > 0.20
