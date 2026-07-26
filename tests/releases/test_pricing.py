"""Pricing over a FAKE posterior with a hand-checkable asymmetric grid."""
import numpy as np
import pandas as pd
import pytest

from wcmodel.releases.pricing import known_team_set, price_fixtures


class FakePost:
    _idx = {"A": 0, "B": 1}
    calls = None

    def __init__(self):
        self.calls = []

    def predict_scoreline(self, home, away, neutral=False, max_goals=10, **kw):
        self.calls.append((home, away, neutral))
        # rows=home goals 0..1, cols=away goals 0..1 — asymmetric on purpose
        return np.array([[0.10, 0.20], [0.30, 0.40]])


def _fx(neutral=False):
    return pd.DataFrame({"date": [pd.Timestamp("2026-09-21")], "home": ["A"],
                         "away": ["B"], "neutral": [neutral]})


def test_grid_conventions():
    r = price_fixtures(FakePost(), _fx(), max_goals=1)[0]
    assert r["one_x_two"]["home"] == pytest.approx(0.30)   # tril
    assert r["one_x_two"]["draw"] == pytest.approx(0.50)   # trace
    assert r["one_x_two"]["away"] == pytest.approx(0.20)   # triu
    assert r["totals"]["over_1_5"] == pytest.approx(0.40)  # P(h+a >= 2)
    assert r["modal_score"] == "1-1" and r["modal_score_p"] == pytest.approx(0.40)
    assert sum(r["one_x_two"].values()) == pytest.approx(1.0, abs=1e-9)


def test_single_call_per_fixture_and_neutral_flag_passthrough():
    """F6: exactly ONE predict call, neutral threaded verbatim — no reverse call."""
    p = FakePost()
    price_fixtures(p, _fx(neutral=True), max_goals=1)
    assert p.calls == [("A", "B", True)]
    p2 = FakePost()
    price_fixtures(p2, _fx(neutral=False), max_goals=1)
    assert p2.calls == [("A", "B", False)]


def test_known_team_set_reads_idx():
    assert known_team_set(FakePost()) == {"A", "B"}


def test_known_team_set_requires_idx():
    with pytest.raises(TypeError, match="_idx"):
        known_team_set(object())
